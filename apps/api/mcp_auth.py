from contextvars import ContextVar
import json
from uuid import UUID, uuid4

from mcp.server.auth.provider import TokenVerifier, AccessToken
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from goodmcp.oauth_store import sha

current_token = ContextVar("hub_verified_token", default=None)


class DatabaseVerifier(TokenVerifier):
    def __init__(self, database, settings): self.database, self.settings = database, settings

    async def verify_token(self, token):
        cached = current_token.get()
        if cached is not None and cached.token == token: return cached
        if not token or not 30 <= len(token) <= 128: return None
        def lookup():
            with self.database.engine.connect() as conn:
                return conn.execute(text("SELECT * FROM hub_access_identity(:hash,:issuer,:resource)"),
                    {"hash": sha(token), "issuer": self.settings.issuer, "resource": self.settings.resource}).mappings().one_or_none()
        row = await run_in_threadpool(lookup)
        if row is None: return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=row["scopes"], expires_at=row["expires_at"],
            resource=row["resource"], subject=str(row["user_id"]),
            claims={"workspace_id": str(row["workspace_id"]), "issuer": row["issuer"]})


class AccessBoundary:
    """Authenticate every protected route, including redirects/aliases, before dispatch."""
    def __init__(self, app, verifier, settings): self.app, self.verifier, self.settings = app, verifier, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http": return await self.app(scope, receive, send)
        headers = {}
        duplicates = set()
        for key, value in scope["headers"]:
            name = key.decode("latin1").lower()
            if name in headers: duplicates.add(name)
            headers[name] = value.decode("latin1")
        path = scope["path"]
        protected = path.startswith(("/mcp", "/api/v1"))

        async def error(status, code, message, *, challenge=False):
            extra = {"Cache-Control": "no-store"}
            if challenge:
                extra["WWW-Authenticate"] = 'Bearer resource_metadata="' + self.settings.base + '/.well-known/oauth-protected-resource/mcp"'
            response = JSONResponse({"error": {"code": code, "message": message, "retryable": status == 503},
                "request_id": str(uuid4())}, status_code=status, headers=extra)
            return await response(scope, receive, send)

        if path not in ("/health/live", "/health/ready"):
            if headers.get("host") != self.settings.authority: return await error(421, "invalid_host", "Unrecognized host")
            if headers.get("origin") and headers["origin"] != self.settings.origin: return await error(403, "forbidden", "Unrecognized origin")
        if not protected: return await self.app(scope, receive, send)
        if duplicates & {"authorization", "x-workspace-id", "host", "origin"}:
            return await error(400, "invalid_input", "Duplicate security header")
        authorization = headers.get("authorization", "")
        if not authorization.startswith("Bearer "): return await error(401, "unauthenticated", "Bearer token required", challenge=True)
        try: token = await self.verifier.verify_token(authorization[7:])
        except Exception: return await error(503, "runtime_unavailable", "Authorization unavailable")
        if token is None: return await error(401, "unauthenticated", "Invalid or expired token", challenge=True)
        if "hub:read" not in token.scopes: return await error(403, "forbidden", "Insufficient scope", challenge=True)
        selected = headers.get("x-workspace-id")
        if selected is not None and selected != token.claims["workspace_id"]:
            return await error(403, "forbidden", "Workspace selection does not match this grant")
        scope.setdefault("state", {})["access_token"] = token
        reset = current_token.set(token)
        try:
            if path.startswith("/mcp"):
                if scope["method"] != "POST": return await error(405, "invalid_input", "Use modern MCP POST")
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect": return
                    body.extend(message.get("body", b""))
                    if len(body) > 1024 * 1024: return await error(413, "invalid_input", "MCP request exceeds 1 MiB")
                    if not message.get("more_body"): break
                try:
                    data = json.loads(body)
                    params = data.get("params", {}) if isinstance(data, dict) else {}
                    modern = params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion")
                    if not modern:
                        response = JSONResponse({"jsonrpc": "2.0", "id": data.get("id") if isinstance(data, dict) else None,
                            "error": {"code": -32022, "message": "Modern MCP 2026-07-28 required; legacy is disabled"}}, status_code=400)
                        return await response(scope, receive, send)
                except (ValueError, TypeError, AttributeError): pass  # SDK handles malformed RPC.
                delivered = False
                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()
                return await self.app(scope, replay, send)
            return await self.app(scope, receive, send)
        finally: current_token.reset(reset)
