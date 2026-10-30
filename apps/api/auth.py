"""OAuth issuer on a separate DB role; browser login/consent, Authlib grant/token/revoke."""
from contextlib import asynccontextmanager
from datetime import timedelta
from html import escape
import json
import os
import re
import secrets
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from authlib.oauth2.rfc6749.errors import OAuth2Error
from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, QueryParams
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import text

from goodmcp.auth_config import AuthSettings, SCOPES
from goodmcp.oauth_store import AuthStore, sha, now
from goodmcp.oauth_server import GrantServer, BufferedRequest
from goodmcp.version import REVISION

COOKIE = "hub_session"


@asynccontextmanager
async def lifespan(app):
    settings = AuthSettings.from_env()
    if not settings.secure_cookie: os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "1"
    app.state.store = AuthStore(settings)
    yield
    app.state.store.engine.dispose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def fail(code, status=400): return JSONResponse({"error": code}, status_code=status, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


def page(title, body):
    return HTMLResponse('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title><main style="max-width:44rem;margin:3rem auto;font:1rem system-ui;padding:1rem">'
        f'<h1>{escape(title)}</h1>{body}</main></html>')


def set_cookie(response, cookie, settings):
    response.set_cookie(COOKIE, cookie, httponly=True, secure=settings.secure_cookie, samesite="lax", path="/auth", max_age=settings.session_ttl)


@app.middleware("http")
async def transport_guards(request, call_next):
    settings = AuthSettings.from_env()
    if len(request.scope.get("query_string", b"")) > 8192: return fail("query_too_large", 414)
    if request.url.path != "/health/ready":
        if request.headers.get("host") != settings.authority: return fail("invalid_host", 421)
        if request.headers.get("origin") and request.headers["origin"] != settings.origin: return fail("invalid_origin", 403)
    # All issuer inputs are bounded, including chunked requests (no reliance on Content-Length).
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384: return fail("request_too_large", 413)
    request._body = bytes(body)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health/ready")
async def health(request: Request):
    try:
        def check():
            with request.app.state.store.engine.connect() as conn:
                return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
        if not await run_in_threadpool(check): return fail("migration_required", 503)
    except Exception: return fail("unavailable", 503)
    return {"status": "ready"}


@app.get("/.well-known/oauth-authorization-server/auth")
@app.get("/auth/.well-known/oauth-authorization-server")
async def metadata(request: Request):
    settings = request.app.state.store.settings
    return {"issuer": settings.issuer, "authorization_endpoint": settings.issuer + "/authorize",
        "token_endpoint": settings.issuer + "/token", "revocation_endpoint": settings.issuer + "/revoke",
        "registration_endpoint": settings.issuer + "/register", "scopes_supported": list(SCOPES),
        "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"], "revocation_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"], "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True}


@app.post("/auth/register")
async def register(request: Request):
    try:
        data = await request.json()
        result = await run_in_threadpool(request.app.state.store.register, data, request.client.host)
        return JSONResponse(result, status_code=201) if result else fail("registration_limit", 429)
    except (ValueError, TypeError, KeyError): return fail("invalid_client_metadata")


def return_target(value):
    if value and value.startswith("/auth/authorize?") and len(value) < 8192 and not re.search(r"[\x00-\x1f\x7f]", value):
        return value
    return None


@app.get("/auth/login")
async def login_form(request: Request):
    store = request.app.state.store
    def create():
        with store.engine.begin() as conn:
            if store.limit(conn, "login-form:" + request.client.host, 100, increment=True, seconds=60): return None
            return store.new_session(conn, pending=return_target(request.query_params.get("return_to")))
    created = await run_in_threadpool(create)
    if created is None: return fail("rate_limited", 429)
    cookie, csrf = created
    response = page("Đăng nhập goodmcp", '<form method="post" action="/auth/login">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<p><label>Email <input name="email" type="email" maxlength="254" autocomplete="username" required></label></p>'
        '<p><label>Mật khẩu <input name="password" type="password" maxlength="1024" autocomplete="current-password" required></label></p>'
        '<button>Đăng nhập</button></form>')
    set_cookie(response, cookie, store.settings)
    return response


@app.post("/auth/login")
async def login(request: Request):
    form = await request.form()
    if len(list(form.multi_items())) != len(form): return fail("duplicate_parameter")
    email, password = str(form.get("email", "")).strip().lower(), str(form.get("password", ""))
    if not 1 <= len(email) <= 254 or not 1 <= len(password) <= 1024: return fail("invalid_login", 401)
    store = request.app.state.store
    result = await run_in_threadpool(store.login, request.cookies.get(COOKIE), str(form.get("csrf", "")), email, password, request.client.host)
    if result["status"] != 303: return fail(result["error"], result["status"])
    response = RedirectResponse(result["next"], status_code=303)
    set_cookie(response, result["cookie"], store.settings)
    return response


def buffered(request, *, query=None, form=None):
    settings = request.app.state.store.settings
    # Build the OAuth URI from configured issuer, not untrusted forwarded headers.
    raw_query = str(query if query is not None else request.query_params)
    url = settings.base + request.url.path + ("?" + raw_query if raw_query else "")
    return BufferedRequest(request.method, url, request.headers, query if query is not None else request.query_params,
                           form if form is not None else FormData())


def validate_authorization(server, req):
    data = req.payload.data
    if any(len(values) > 1 for values in req.payload.datalist.values()): raise ValueError("duplicate_parameter")
    if data.get("resource") != server.settings.resource or data.get("code_challenge_method") != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", data.get("code_challenge", "")):
        raise ValueError("invalid_request")
    if not data.get("redirect_uri"): raise ValueError("redirect_required")
    client = server.query_client(data.get("client_id"))
    if client is None or not client.check_redirect_uri(data["redirect_uri"]): raise ValueError("invalid_client_or_redirect")
    if set((data.get("scope") or "hub:read").split()) - set(client.row["allowed_scopes"]): raise ValueError("invalid_scope")
    return server.get_consent_grant(req)


@app.get("/auth/authorize")
async def authorize_form(request: Request):
    store = request.app.state.store
    def render():
        with store.engine.begin() as conn:
            session = store.session(conn, request.cookies.get(COOKIE), lock=True)
            if not session or not session["user_id"]:
                return RedirectResponse("/auth/login?" + urlencode({"return_to": "/auth/authorize?" + str(request.query_params)}), status_code=303)
            server = GrantServer(store, conn, allow_client_fetch=True)
            req = buffered(request)
            try: grant = validate_authorization(server, req)
            except (OAuth2Error, ValueError): return fail("invalid_authorization_request")
            memberships = store.memberships(conn, session["user_id"])
            if not memberships: return fail("no_workspace", 403)
            csrf = secrets.token_urlsafe(32)
            conn.execute(text("UPDATE auth_browser_sessions SET csrf_hash=:csrf,pending_authorize=:pending WHERE id=:id"),
                         {"csrf": sha(csrf), "pending": "/auth/authorize?" + str(request.query_params), "id": session["id"]})
            options = "".join(f'<option value="{m["workspace_id"]}">{escape(m["name"])} ({m["role"]})</option>' for m in memberships)
            return page("Cấp quyền kết nối", f'<p>Ứng dụng: <strong>{escape(req.client.row["name"])}</strong></p>'
                f'<p>Quyền yêu cầu: {escape(req.scope)}</p><p>Máy chủ: {escape(store.settings.resource)}</p>'
                '<form method="post" action="/auth/authorize">'
                f'<input name="csrf" type="hidden" value="{csrf}"><label>Vùng dữ liệu <select name="workspace_id">{options}</select></label>'
                '<p><button name="consent" value="allow">Cho phép</button> <button name="consent" value="deny">Từ chối</button></p></form>')
    return await run_in_threadpool(render)


@app.post("/auth/authorize")
async def authorize(request: Request):
    form = await request.form()
    if len(list(form.multi_items())) != len(form): return fail("duplicate_parameter")
    store = request.app.state.store
    def issue():
        with store.engine.begin() as conn:
            session = store.session(conn, request.cookies.get(COOKIE), lock=True)
            if not session or not session["user_id"] or not store.check_csrf(session, form.get("csrf")) or not session["pending_authorize"]:
                return fail("csrf_or_session", 403)
            params = QueryParams(urlsplit(session["pending_authorize"]).query)
            req = buffered(request, query=params, form=FormData())
            server = GrantServer(store, conn, allow_client_fetch=True)
            try: grant = validate_authorization(server, req)
            except (OAuth2Error, ValueError): return fail("invalid_authorization_request")
            try: workspace = UUID(str(form.get("workspace_id", "")))
            except ValueError: return fail("invalid_workspace", 403)
            member = next((m for m in store.memberships(conn, session["user_id"]) if m["workspace_id"] == workspace), None)
            if member is None: return fail("invalid_workspace", 403)
            if member["role"] == "viewer" and set(req.scope.split()) & {"hub:write", "tools:run", "projects:write"}: return fail("invalid_scope", 403)
            conn.execute(text("UPDATE auth_browser_sessions SET pending_authorize=NULL,csrf_hash=:hash WHERE id=:id"),
                         {"id": session["id"], "hash": sha(secrets.token_urlsafe(32))})
            req.approved_workspace = workspace
            # Authlib validates PKCE/redirect and issues an RFC9207 issuer-bound code response.
            return server.create_authorization_response(req, grant_user=session["user_id"] if form.get("consent") == "allow" else None, grant=grant)
    return await run_in_threadpool(issue)


@app.get("/auth/account")
async def account(request: Request):
    store = request.app.state.store
    def render():
        with store.engine.begin() as conn:
            session = store.session(conn, request.cookies.get(COOKIE), lock=True)
            if not session or not session["user_id"]: return RedirectResponse("/auth/login", status_code=303)
            csrf = secrets.token_urlsafe(32)
            conn.execute(text("UPDATE auth_browser_sessions SET csrf_hash=:hash,pending_authorize=NULL WHERE id=:id"), {"hash": sha(csrf), "id": session["id"]})
            return page("Đã đăng nhập", '<p>Mở kết nối MCP từ client để chọn vùng dữ liệu và cấp quyền.</p>'
                f'<form method="post" action="/auth/logout"><input name="csrf" type="hidden" value="{csrf}"><button>Đăng xuất</button></form>')
    return await run_in_threadpool(render)


@app.post("/auth/logout")
async def logout(request: Request):
    form = await request.form()
    store = request.app.state.store
    def clear():
        with store.engine.begin() as conn:
            session = store.session(conn, request.cookies.get(COOKIE), lock=True)
            if not store.check_csrf(session, form.get("csrf")): return fail("csrf", 403)
            conn.execute(text("DELETE FROM auth_browser_sessions WHERE id=:id"), {"id": session["id"]})
            response = RedirectResponse("/auth/login", status_code=303)
            response.delete_cookie(COOKIE, path="/auth", secure=store.settings.secure_cookie, httponly=True, samesite="lax")
            return response
    return await run_in_threadpool(clear)


@app.post("/auth/token")
@app.post("/auth/revoke")
async def token_or_revoke(request: Request):
    form = await request.form()
    if request.query_params or len(list(form.multi_items())) != len(form): return fail("duplicate_or_query_parameter")
    store = request.app.state.store
    revoke = request.url.path.endswith("/revoke")
    if not revoke and form.get("resource") != store.settings.resource: return fail("invalid_target")
    def exchange():
        with store.engine.begin() as conn:
            # Permit CIMD refresh only with an existing unexpired credential bound to this client.
            supplied = form.get("code") if form.get("grant_type") == "authorization_code" else form.get("refresh_token")
            allowed = False
            if supplied:
                table, column = ("oauth_codes", "code_hash") if form.get("grant_type") == "authorization_code" else ("tokens", "token_hash")
                allowed = bool(conn.execute(text(f"""SELECT 1 FROM {table} v JOIN oauth_grants g ON g.id=v.grant_id
                    WHERE v.{column}=:hash AND g.client_id=:client AND v.expires_at>now() AND v.consumed_at IS NULL AND g.revoked_at IS NULL"""),
                    {"hash": sha(str(supplied)), "client": form.get("client_id")}).first())
            server = GrantServer(store, conn, allow_client_fetch=allowed)
            req = buffered(request, form=form)
            return server.create_endpoint_response("revocation", req) if revoke else server.create_token_response(req)
    return await run_in_threadpool(exchange)


@app.exception_handler(Exception)
async def internal_error(request: Request, exc):
    # Never emit credential-bearing request bodies, SQL parameters or Authlib traceback.
    return fail("server_error", 500)
