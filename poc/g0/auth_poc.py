"""Loopback-only OAuth/Authlib ASGI adapter + official MCP v2 resource server.

One pre-registered public client, one pre-approved owner/workspace; in-memory
credentials/grants die on exit. No refresh, signup, dynamic registration, DB or
production consent UI. This is deliberately separate from the future core.
"""
import hmac
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from authlib.oauth2.rfc6749 import AuthorizationServer, OAuth2Payload, OAuth2Request, ClientMixin, AuthorizationCodeMixin
from authlib.oauth2.rfc6749.errors import OAuth2Error
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant
from authlib.oauth2.rfc7636 import CodeChallenge
from fastapi import FastAPI, Request
from starlette.datastructures import FormData
from starlette.responses import HTMLResponse, JSONResponse, Response
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, BaseModel, Field

from runtime import load

BASE = "http://127.0.0.1:8765"
RESOURCE = BASE + "/mcp"
CALLBACK = BASE + "/callback"
SCOPE = "hub:read"
OWNER = {"user_id": "g0-owner", "workspace_id": "g0-workspace-a"}
password = os.environ["G0_OWNER_PASSWORD"]
codes, tokens, sessions, login_nonces = {}, {}, {}, {}


class PublicClient(ClientMixin):
    client_id = "g0-local-client"

    def get_client_id(self): return self.client_id
    def get_default_redirect_uri(self): return CALLBACK
    def get_allowed_scope(self, scope): return scope or SCOPE
    def check_redirect_uri(self, uri): return uri == CALLBACK
    def check_client_secret(self, secret): return False
    def check_endpoint_auth_method(self, method, endpoint): return endpoint == "token" and method == "none"
    def check_response_type(self, value): return value == "code"
    def check_grant_type(self, value): return value == "authorization_code"


class Payload(OAuth2Payload):
    def __init__(self, values): self.values = values

    @property
    def data(self): return self.values

    @property
    def datalist(self):
        result = defaultdict(list)
        for k, v in self.values.multi_items(): result[k].append(v)
        return result


class BufferedOAuthRequest(OAuth2Request):
    def __init__(self, request, form):
        super().__init__(request.method, str(request.url), headers=request.headers)
        self._args, self._form = request.query_params, form
        self.payload = Payload(FormData(list(self._args.multi_items()) + list(form.multi_items())))

    @property
    def args(self): return self._args

    @property
    def form(self): return self._form


@dataclass
class Code(AuthorizationCodeMixin):
    code: str
    client_id: str
    redirect_uri: str
    scope: str
    code_challenge: str
    code_challenge_method: str
    expires: float
    user: dict

    def get_redirect_uri(self): return self.redirect_uri
    def get_scope(self): return self.scope


class Grant(AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def save_authorization_code(self, code, request):
        data = request.payload.data
        codes[code] = Code(code, request.client.client_id, data["redirect_uri"], request.scope,
                           data["code_challenge"], data["code_challenge_method"], time.time() + 60, request.user)

    def query_authorization_code(self, code, client):
        item = codes.get(code)
        return item if item and item.client_id == client.client_id and item.expires > time.time() else None

    def delete_authorization_code(self, code): codes.pop(code.code, None)
    def authenticate_user(self, code): return code.user


class S256Only(CodeChallenge):
    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]


class ASGIAuthServer(AuthorizationServer):
    def query_client(self, client_id):
        return PublicClient() if client_id == PublicClient.client_id else None

    def save_token(self, token, request):
        tokens[token["access_token"]] = {"client_id": request.client.client_id,
            "scope": token["scope"], "expires_at": int(time.time()) + token["expires_in"],
            "resource": RESOURCE, **request.user}

    def create_oauth2_request(self, request): return request

    def handle_response(self, status, body, headers):
        response = JSONResponse(body, status_code=status) if isinstance(body, dict) else Response(body, status_code=status)
        for key, value in headers: response.headers[key] = value
        return response

    def send_signal(self, name, *args, **kwargs): pass


oauth = ASGIAuthServer(scopes_supported=[SCOPE])
oauth.register_grant(Grant, [S256Only(required=True)])


def generate_token(**kwargs):
    return {"access_token": secrets.token_urlsafe(32), "token_type": "Bearer", "expires_in": 300,
            "scope": kwargs["scope"]}


oauth.register_token_generator("default", generate_token)


class Verifier(TokenVerifier):
    async def verify_token(self, token):
        item = tokens.get(token)
        if not item or item["expires_at"] <= time.time() or item["workspace_id"] != OWNER["workspace_id"]:
            return None
        return AccessToken(token=token, client_id=item["client_id"], scopes=item["scope"].split(),
                           expires_at=item["expires_at"], resource=item["resource"], subject=item["user_id"],
                           claims={"workspace_id": item["workspace_id"]})


mcp = MCPServer("goodmcp-g0", version="0.0.1", token_verifier=Verifier(),
                auth=AuthSettings(issuer_url=AnyHttpUrl(BASE), resource_server_url=AnyHttpUrl(RESOURCE),
                                  required_scopes=[SCOPE], validate_token_resource=True))
calc = load("calculators")


class CITResult(BaseModel):
    currency: str
    cit_with_incentive_VND: int
    effective_rate_pct: float


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                     idempotent_hint=True, open_world_hint=False))
def g0_cit(revenue: Annotated[float, Field(ge=0, le=1e15, allow_inf_nan=False)],
           cost: Annotated[float, Field(ge=0, le=1e15, allow_inf_nan=False)]) -> CITResult:
    """Local PoC only: call the original reviewed Python CIT calculator at 20%."""
    return CITResult.model_validate(calc.cit_estimate(revenue, cost))


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run(): yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def loopback_only(request, call_next):
    if request.headers.get("host") != "127.0.0.1:8765":
        return JSONResponse({"error": "invalid_host"}, status_code=421)
    origin = request.headers.get("origin")
    if origin and origin != BASE:
        return JSONResponse({"error": "invalid_origin"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health(): return {"status": "local-poc"}


@app.get("/.well-known/oauth-authorization-server")
async def metadata():
    return {"issuer": BASE, "authorization_endpoint": BASE + "/authorize", "token_endpoint": BASE + "/token",
            "response_types_supported": ["code"], "grant_types_supported": ["authorization_code"],
            "token_endpoint_auth_methods_supported": ["none"], "code_challenge_methods_supported": ["S256"],
            "scopes_supported": [SCOPE]}


@app.get("/login")
async def login_form():
    nonce = secrets.token_urlsafe(32)
    login_nonces[nonce] = time.time() + 60
    response = HTMLResponse(f'<form method="post"><input name="csrf" type="hidden" value="{nonce}">'
                            '<input name="password" type="password"><button>Login local owner</button></form>')
    response.set_cookie("g0-csrf", nonce, httponly=True, samesite="strict", max_age=60)
    return response


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    nonce = str(form.get("csrf", ""))
    expiry = login_nonces.pop(nonce, 0)
    if expiry <= time.time() or not hmac.compare_digest(nonce, request.cookies.get("g0-csrf", "")):
        return JSONResponse({"error": "csrf"}, status_code=403)
    if not hmac.compare_digest(str(form.get("password", "")), password):
        return JSONResponse({"error": "invalid_login"}, status_code=401)
    sid = secrets.token_urlsafe(32)
    sessions[sid] = time.time() + 300
    response = JSONResponse({"user_id": OWNER["user_id"]})
    response.set_cookie("g0-session", sid, httponly=True, samesite="strict", max_age=300)
    response.delete_cookie("g0-csrf")
    return response


@app.get("/authorize")
async def authorize(request: Request):
    if sessions.get(request.cookies.get("g0-session"), 0) <= time.time():
        return JSONResponse({"error": "login_required"}, status_code=401)
    # S256/resource required even if Authlib would permit an absent challenge.
    params = request.query_params
    if params.get("resource") != RESOURCE or params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    req = BufferedOAuthRequest(request, FormData())
    try:
        grant = oauth.get_authorization_grant(req)
        return oauth.create_authorization_response(req, grant_user=OWNER, grant=grant)
    except OAuth2Error as error:
        return oauth.handle_error_response(req, error)


@app.post("/token")
async def token(request: Request):
    form = await request.form()
    if form.get("resource") != RESOURCE:
        return JSONResponse({"error": "invalid_target"}, status_code=400)
    return oauth.create_token_response(BufferedOAuthRequest(request, form))


# Keep custom routes before Mount('/'). SDK routes protect /mcp, not custom routes.
app.mount("/", mcp.streamable_http_app(stateless_http=True, json_response=True,
          transport_security=TransportSecuritySettings(allowed_hosts=["127.0.0.1:8765"], allowed_origins=[BASE])))
