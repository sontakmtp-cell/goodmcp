"""Issuer-only persistence. The API never receives this role's credential."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import threading
from uuid import uuid4

from sqlalchemy import create_engine, text
from .config import database_url
from .auth_config import AuthSettings
from .oauth_clients import validate_metadata, validate_cimd_metadata, fetch_cimd
from .passwords import password_hash, verify_password, hasher


def sha(value): return hashlib.sha256(value.encode()).hexdigest()
def now(): return datetime.now(timezone.utc)


class LoginBusy(Exception): pass


class AuthStore:
    def __init__(self, settings=None):
        self.settings = settings or AuthSettings.from_env()
        self.engine = create_engine(database_url("auth"), pool_size=5, max_overflow=0, pool_pre_ping=True,
                                    hide_parameters=True, connect_args={"connect_timeout": 3})
        self.hash_slots = threading.BoundedSemaphore(2)
        self.dummy_hash = password_hash("dummy-non-account-password")

    def session(self, conn, cookie, *, lock=False):
        if not cookie or not 30 <= len(cookie) <= 128: return None
        query = "SELECT * FROM auth_browser_sessions WHERE token_hash=:hash AND expires_at>now()"
        if lock: query += " FOR UPDATE"
        return conn.execute(text(query), {"hash": sha(cookie)}).mappings().one_or_none()

    def new_session(self, conn, user_id=None, pending=None):
        cookie, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        conn.execute(text("DELETE FROM auth_browser_sessions WHERE expires_at<now()"))
        conn.execute(text("""INSERT INTO auth_browser_sessions(token_hash,user_id,csrf_hash,pending_authorize,expires_at)
            VALUES(:hash,:user,:csrf,:pending,:expiry)"""),
            {"hash": sha(cookie), "user": user_id, "csrf": sha(csrf), "pending": pending,
             "expiry": now() + timedelta(seconds=self.settings.session_ttl)})
        return cookie, csrf

    def check_csrf(self, session, csrf):
        return session is not None and isinstance(csrf, str) and hmac.compare_digest(session["csrf_hash"], sha(csrf))

    def limit(self, conn, bucket, maximum, *, increment=False, seconds=900):
        key = sha(bucket)
        if increment:
            conn.execute(text("DELETE FROM auth_login_limits WHERE expires_at<now()"))
            conn.execute(text("""INSERT INTO auth_login_limits(bucket,attempts,expires_at) VALUES(:key,1,:expiry)
                ON CONFLICT(bucket) DO UPDATE SET attempts=CASE WHEN auth_login_limits.expires_at<=now() THEN 1 ELSE auth_login_limits.attempts+1 END,
                expires_at=CASE WHEN auth_login_limits.expires_at<=now() THEN EXCLUDED.expires_at ELSE auth_login_limits.expires_at END"""),
                {"key": key, "expiry": now() + timedelta(seconds=seconds)})
        attempts = conn.execute(text("SELECT attempts FROM auth_login_limits WHERE bucket=:key AND expires_at>now()"), {"key": key}).scalar_one_or_none()
        return (attempts or 0) >= maximum

    def login(self, cookie, csrf, email, password, peer):
        with self.engine.begin() as conn:
            session = self.session(conn, cookie, lock=True)
            if not self.check_csrf(session, csrf): return {"status": 403, "error": "csrf"}
            account_bucket, ip_bucket = "login-account:" + email, "login-ip:" + peer
            if self.limit(conn, account_bucket, 5) or self.limit(conn, ip_bucket, 30):
                return {"status": 429, "error": "rate_limited"}
            user = conn.execute(text("SELECT id,password_hash FROM users WHERE lower(email)=:email AND active"), {"email": email}).mappings().one_or_none()
            if not self.hash_slots.acquire(blocking=False): return {"status": 429, "error": "login_busy"}
            try:
                valid = verify_password(user["password_hash"] if user else self.dummy_hash, password)
                if valid and user and (not user["password_hash"].startswith("$argon2id$") or hasher.check_needs_rehash(user["password_hash"])):
                    conn.execute(text("UPDATE users SET password_hash=:hash WHERE id=:id"), {"hash": password_hash(password), "id": user["id"]})
            finally: self.hash_slots.release()
            if not valid or user is None:
                self.limit(conn, account_bucket, 5, increment=True)
                self.limit(conn, ip_bucket, 30, increment=True)
                return {"status": 401, "error": "invalid_login"}
            conn.execute(text("DELETE FROM auth_login_limits WHERE bucket=:key"), {"key": sha(account_bucket)})
            conn.execute(text("DELETE FROM auth_browser_sessions WHERE id=:id"), {"id": session["id"]})
            new_cookie, _ = self.new_session(conn, user["id"], session["pending_authorize"])
            return {"status": 303, "cookie": new_cookie, "next": session["pending_authorize"] or "/auth/account"}

    def memberships(self, conn, user_id):
        return conn.execute(text("""SELECT m.id,m.workspace_id,m.role,w.name FROM memberships m JOIN workspaces w ON w.id=m.workspace_id
            JOIN users u ON u.id=m.user_id AND u.active WHERE m.user_id=:user AND m.active ORDER BY w.name"""), {"user": user_id}).mappings().all()

    def client(self, conn, client_id, *, allow_fetch=False):
        if not client_id or len(client_id) > 2048: return None
        row = conn.execute(text("SELECT * FROM oauth_clients WHERE client_id=:id AND active"), {"id": client_id}).mappings().one_or_none()
        if row and (row["metadata_expires_at"] is None or row["metadata_expires_at"] > now()): return row
        if allow_fetch and client_id.startswith("https://"):
            if row is None and conn.execute(text("SELECT count(*) FROM oauth_clients")).scalar_one() >= 500: return None
            try:
                raw = fetch_cimd(client_id)
                data = validate_cimd_metadata(raw, allow_loopback=not self.settings.secure_cookie)
            except Exception: return None
            conn.execute(text("""INSERT INTO oauth_clients(client_id,name,redirect_uris,allowed_scopes,source,metadata_expires_at)
                VALUES(:id,:name,CAST(:redirects AS jsonb),CAST(:scopes AS jsonb),'cimd',:expiry)
                ON CONFLICT(client_id) DO UPDATE SET name=EXCLUDED.name,redirect_uris=EXCLUDED.redirect_uris,
                allowed_scopes=EXCLUDED.allowed_scopes,metadata_expires_at=EXCLUDED.metadata_expires_at WHERE oauth_clients.source='cimd' AND oauth_clients.active"""),
                {"id": client_id, "name": data["name"], "redirects": json.dumps(data["redirect_uris"]),
                 "scopes": json.dumps(data["allowed_scopes"]), "expiry": now() + timedelta(hours=1)})
            return conn.execute(text("SELECT * FROM oauth_clients WHERE client_id=:id AND active"), {"id": client_id}).mappings().one_or_none()
        return None

    def register(self, data, peer):
        validated = validate_metadata(data, allow_loopback=not self.settings.secure_cookie)
        with self.engine.begin() as conn:
            if self.limit(conn, "dcr:" + peer, 20, increment=True, seconds=3600): return None
            if conn.execute(text("SELECT count(*) FROM oauth_clients")).scalar_one() >= 500: return None
            client_id = "hub-client-" + secrets.token_urlsafe(24)
            conn.execute(text("""INSERT INTO oauth_clients(client_id,name,redirect_uris,allowed_scopes,source)
                VALUES(:id,:name,CAST(:redirects AS jsonb),CAST(:scopes AS jsonb),'dcr')"""),
                {"id": client_id, "name": validated["name"], "redirects": json.dumps(validated["redirect_uris"]), "scopes": json.dumps(validated["allowed_scopes"])})
        return {"client_id": client_id, "client_name": validated["name"], "redirect_uris": validated["redirect_uris"],
                "scope": " ".join(validated["allowed_scopes"]), "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}


def revoke_family(conn, grant_id):
    conn.execute(text("UPDATE oauth_grants SET revoked_at=COALESCE(revoked_at,now()) WHERE id=:id"), {"id": grant_id})
    conn.execute(text("UPDATE tokens SET revoked_at=COALESCE(revoked_at,now()) WHERE grant_id=:id"), {"id": grant_id})


def active_grant(conn, grant_id):
    return conn.execute(text("""SELECT g.* FROM oauth_grants g JOIN users u ON u.id=g.user_id AND u.active
        JOIN memberships m ON m.user_id=g.user_id AND m.workspace_id=g.workspace_id AND m.active
        WHERE g.id=:id AND g.revoked_at IS NULL FOR UPDATE OF g"""), {"id": grant_id}).mappings().one_or_none()
