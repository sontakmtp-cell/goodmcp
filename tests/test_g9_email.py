import json
import smtplib
from uuid import uuid4

import pytest

from goodmcp.email_worker import SMTPConfig, EmailWorker, configuration, error_code, send_message


def test_unconfigured_smtp_keeps_queue_untouched(monkeypatch):
    monkeypatch.delenv("HUB_SMTP_CONFIG_FILE", raising=False)
    assert configuration() is None
    assert EmailWorker(None, None).process_one() == {"status": "unconfigured"}


def test_smtp_configuration_requires_tls_and_single_email(tmp_path, monkeypatch):
    path = tmp_path / "smtp.json"
    monkeypatch.setenv("HUB_SMTP_CONFIG_FILE", str(path))
    data = {"host": "smtp.example.org", "sender": "noreply@example.org", "username": "user", "password": "private"}
    path.write_text(json.dumps(data))
    config = configuration()
    assert config.security == "starttls" and config.port == 587
    assert "private" not in repr(config)
    for changed in ({"security": "none"}, {"port": True}, {"timeout": 100}, {"sender": "one@example.org,two@example.org"},
                    {"username": ""}, {"host": "https://smtp.example.org"}):
        path.write_text(json.dumps({**data, **changed}))
        with pytest.raises(ValueError):
            configuration()


@pytest.mark.parametrize("security", ["ssl", "starttls"])
def test_smtp_message_uses_tls_explicit_recipient_and_stable_id(security):
    events, messages = [], []
    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            assert host == "smtp.example.org" and kwargs["timeout"] == 10
            assert ("context" in kwargs) == (security == "ssl")
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def ehlo(self): events.append("ehlo")
        def starttls(self, **kwargs):
            assert kwargs["context"].check_hostname
            events.append("tls")
        def login(self, username, password):
            assert (username, password) == ("user", "private")
            events.append("login")
        def send_message(self, message, **kwargs):
            assert kwargs == {"from_addr": "noreply@example.org", "to_addrs": ["recipient@example.org"]}
            events.append("send")
            messages.append(message)
            return {}
    row = {"id": uuid4(), "recipient": "recipient@example.org", "subject": "Lời mời", "body": "https://goodmcp.si/app/invitations?token=private"}
    config = SMTPConfig("smtp.example.org", 465 if security == "ssl" else 587, "noreply@example.org", "user", "private", security)
    send_message(config, row, smtp_factory=FakeSMTP)
    send_message(config, row, smtp_factory=FakeSMTP)
    assert messages[0]["Message-ID"] == messages[1]["Message-ID"]
    assert ("tls" in events) == (security == "starttls")
    assert events.index("login") < events.index("send")


def test_smtp_error_codes_do_not_include_server_or_credential_text():
    for exception, expected in ((smtplib.SMTPAuthenticationError(535, b"private"), "smtp_auth_failed"),
                                (smtplib.SMTPRecipientsRefused({"private@example.org": (550, b"private")}), "smtp_recipient_rejected"),
                                (TimeoutError("private"), "smtp_unavailable"), (ValueError("private"), "smtp_delivery_failed")):
        assert error_code(exception) == expected
        assert "private" not in error_code(exception)
