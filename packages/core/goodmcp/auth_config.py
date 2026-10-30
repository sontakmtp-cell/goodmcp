from dataclasses import dataclass
import os
from urllib.parse import urlsplit

SCOPES = ("hub:read", "tools:run", "projects:read", "projects:write")


@dataclass(frozen=True)
class AuthSettings:
    base: str
    issuer: str
    resource: str
    authority: str
    origin: str
    secure_cookie: bool
    access_ttl: int = 300
    refresh_ttl: int = 604800
    session_ttl: int = 1800
    code_ttl: int = 120

    @classmethod
    def from_env(cls):
        base = os.environ.get("HUB_PUBLIC_BASE_URL", "http://127.0.0.1:18080").rstrip("/")
        p = urlsplit(base)
        local = p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost") and os.environ.get("HUB_ALLOW_HTTP_LOOPBACK") == "1"
        if (p.scheme != "https" and not local) or p.username or p.password or p.path or p.query or p.fragment or not p.hostname:
            raise RuntimeError("Configure an HTTPS public base URL; HTTP is only explicitly allowed for loopback")
        return cls(base, base + "/auth", base + "/mcp", p.netloc, f"{p.scheme}://{p.netloc}", not local)
