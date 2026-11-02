"""SMTP consumer for the private invitation outbox.

Queue insertion and invitation creation are atomic. SMTP delivery is at least
once: a crash after the remote server accepts mail but before database commit
can deliver a duplicate message. A stable Message-ID aids mail-server deduping.
"""
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage
import json
import os
from pathlib import Path
import signal
import smtplib
import ssl
import threading

from sqlalchemy import text

from .oauth_store import AuthStore, now
from .workspace_admin import clean_email


MAX_ATTEMPTS = 8


@dataclass(frozen=True, repr=False)
class SMTPConfig:
    host: str
    port: int
    sender: str
    username: str = ""
    password: str = ""
    security: str = "starttls"
    timeout: int = 10


def configuration():
    filename = os.environ.get("HUB_SMTP_CONFIG_FILE")
    if not filename:
        return None
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid SMTP configuration")
    host = data.get("host", "")
    security = data.get("security", "starttls")
    port = data.get("port", 465 if security == "ssl" else 587)
    timeout = data.get("timeout", 10)
    if not isinstance(host, str) or not host or len(host) > 253 or any(c.isspace() or c in "/\\@" for c in host):
        raise ValueError("Invalid SMTP host")
    if security not in {"ssl", "starttls"}:
        raise ValueError("SMTP requires TLS")
    if type(port) is not int or not 1 <= port <= 65535 or type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError("Invalid SMTP port or timeout")
    username, password = data.get("username", ""), data.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str) or bool(username) != bool(password):
        raise ValueError("Invalid SMTP credentials")
    return SMTPConfig(host, port, clean_email(data.get("sender")), username, password, security, timeout)


def send_message(config, row, *, smtp_factory=None):
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = clean_email(row["recipient"])
    message["Subject"] = row["subject"]
    message["Message-ID"] = "<" + str(row["id"]) + "@" + config.sender.rsplit("@", 1)[1] + ">"
    message.set_content(row["body"])
    context = ssl.create_default_context()
    if config.security == "ssl":
        factory = smtp_factory or smtplib.SMTP_SSL
        smtp = factory(config.host, config.port, timeout=config.timeout, context=context)
    else:
        factory = smtp_factory or smtplib.SMTP
        smtp = factory(config.host, config.port, timeout=config.timeout)
    with smtp:
        smtp.ehlo()
        if config.security == "starttls":
            smtp.starttls(context=context)
            smtp.ehlo()
        if config.username:
            smtp.login(config.username, config.password)
        refused = smtp.send_message(message, from_addr=config.sender, to_addrs=[row["recipient"]])
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def error_code(exc):
    # Never persist exception text: SMTP libraries may include server echoes,
    # addresses, authentication details, or credential-bearing config values.
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "smtp_auth_failed"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "smtp_recipient_rejected"
    if isinstance(exc, (TimeoutError, OSError)):
        return "smtp_unavailable"
    return "smtp_delivery_failed"


class EmailWorker:
    def __init__(self, store, config, *, sender=send_message):
        self.store, self.config, self.sender = store, config, sender

    def process_one(self):
        if self.config is None:
            return {"status": "unconfigured"}
        with self.store.engine.begin() as c:
            row = c.execute(text("""SELECT id,recipient,subject,body,attempts FROM email_outbox
                WHERE sent_at IS NULL AND attempts<:maximum AND next_attempt_at<=now()
                ORDER BY next_attempt_at,id FOR UPDATE SKIP LOCKED LIMIT 1"""), {"maximum": MAX_ATTEMPTS}).mappings().one_or_none()
            if row is None:
                return {"status": "idle"}
            attempt = row["attempts"] + 1
            try:
                self.sender(self.config, row)
            except Exception as exc:
                code = error_code(exc)
                delay = min(3600, 30 * 2 ** (attempt - 1))
                c.execute(text("""UPDATE email_outbox SET attempts=:attempt,last_error=:error,next_attempt_at=:next
                    WHERE id=:id"""), {"id": row["id"], "attempt": attempt, "error": code,
                        "next": now() + timedelta(seconds=delay)})
                return {"status": "exhausted" if attempt >= MAX_ATTEMPTS else "retry", "error": code}
            c.execute(text("UPDATE email_outbox SET attempts=:attempt,sent_at=now(),last_error=NULL,body='' WHERE id=:id"),
                      {"id": row["id"], "attempt": attempt})
            return {"status": "sent"}


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    store = AuthStore()
    try:
        try:
            config = configuration()
        except Exception:
            print(json.dumps({"service": "email", "status": "invalid_configuration"}), flush=True)
            return 1
        worker = EmailWorker(store, config)
        print(json.dumps({"service": "email", "status": "ready" if config else "unconfigured"}), flush=True)
        while not stop.is_set():
            try:
                result = worker.process_one()
            except Exception:
                result = {"status": "database_unavailable"}
            if result["status"] in {"retry", "exhausted", "database_unavailable"}:
                print(json.dumps({"service": "email", **result}), flush=True)
            stop.wait(0.1 if result["status"] == "sent" else 2)
    finally:
        store.engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
