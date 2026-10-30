"""Authlib grants over one database transaction per HTTP operation.

Row locks make code consumption/refresh rotation/replay revocation atomic. Error
responses commit replay revocations; exceptions roll back incomplete issuance.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
import json
import secrets
from uuid import uuid4

from authlib.oauth2.rfc6749 import AuthorizationServer, OAuth2Request, OAuth2Payload, ClientMixin, AuthorizationCodeMixin
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc6749.errors import InvalidGrantError
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc9207 import IssuerParameter
from starlette.responses import Response
from starlette.datastructures import FormData
from sqlalchemy import text

from .auth_config import SCOPES
from .oauth_store import sha, now, active_grant, revoke_family


class Client(ClientMixin):
    def __init__(self, row): self.row, self.client_id = row, row["client_id"]
    def get_client_id(self): return self.client_id
    def get_default_redirect_uri(self): return self.row["redirect_uris"][0]
    def check_redirect_uri(self, uri): return uri in self.row["redirect_uris"]
    def get_allowed_scope(self, scope): return scope or "hub:read"
    def check_client_secret(self, secret): return False
    def check_endpoint_auth_method(self, method, endpoint): return method == "none" and endpoint in ("token", "revocation")
    def check_response_type(self, value): return value == "code"
    def check_grant_type(self, value): return value in ("authorization_code", "refresh_token")


class Payload(OAuth2Payload):
    def __init__(self, data): self.values = data
    @property
    def data(self): return self.values
    @property
    def datalist(self):
        out = defaultdict(list)
        for key, value in self.values.multi_items(): out[key].append(value)
        return out


class BufferedRequest(OAuth2Request):
    def __init__(self, method, url, headers, query, form):
        super().__init__(method, url, headers=headers)
        self._args, self._form = query, form
        self.payload = Payload(FormData(list(query.multi_items()) + list(form.multi_items())))
        self.approved_workspace = None
    @property
    def args(self): return self._args
    @property
    def form(self): return self._form


class OAuthResponse(Response):
    def __init__(self, status, body, headers):
        super().__init__(json.dumps(body) if isinstance(body, dict) else body, status_code=status,
                         headers=dict(headers), media_type="application/json" if isinstance(body, dict) else None)
    @property
    def location(self): return self.headers.get("location")
    @location.setter
    def location(self, value): self.headers["location"] = value


@dataclass
class CodeCredential(AuthorizationCodeMixin):
    row: dict
    grant: dict
    @property
    def code_challenge(self): return self.row["code_challenge"]
    @property
    def code_challenge_method(self): return self.row["code_challenge_method"]
    def get_redirect_uri(self): return self.row["redirect_uri"]
    def get_scope(self): return " ".join(self.grant["scopes"])


@dataclass
class TokenCredential:
    row: dict
    grant: dict
    def check_client(self, client): return self.grant["client_id"] == client.client_id
    def get_scope(self): return " ".join(self.row["scopes"])


class S256(CodeChallenge):
    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]


class CodeGrant(AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def save_authorization_code(self, code, request):
        grant_id = uuid4()
        request.grant_id = grant_id
        c = self.server.conn
        c.execute(text("""INSERT INTO oauth_grants(id,workspace_id,user_id,client_id,scopes,issuer,resource)
            VALUES(:id,:ws,:user,:client,CAST(:scopes AS jsonb),:issuer,:resource)"""),
            {"id": grant_id, "ws": request.approved_workspace, "user": request.user, "client": request.client.client_id,
             "scopes": json.dumps(request.scope.split()), "issuer": self.server.settings.issuer, "resource": self.server.settings.resource})
        c.execute(text("""INSERT INTO oauth_codes(workspace_id,grant_id,code_hash,redirect_uri,code_challenge,code_challenge_method,expires_at)
            VALUES(:ws,:grant,:hash,:redirect,:challenge,'S256',:expiry)"""),
            {"ws": request.approved_workspace, "grant": grant_id, "hash": sha(code),
             "redirect": request.payload.redirect_uri, "challenge": request.payload.data["code_challenge"],
             "expiry": now() + timedelta(seconds=self.server.settings.code_ttl)})

    def query_authorization_code(self, code, client):
        c = self.server.conn
        row = c.execute(text("SELECT * FROM oauth_codes WHERE code_hash=:hash"), {"hash": sha(code)}).mappings().one_or_none()
        if row is None: return None
        grant = active_grant(c, row["grant_id"])
        if grant is None or grant["client_id"] != client.client_id: return None
        row = c.execute(text("SELECT * FROM oauth_codes WHERE id=:id FOR UPDATE"), {"id": row["id"]}).mappings().one()
        if row["consumed_at"] is not None:
            revoke_family(c, row["grant_id"])
            return None
        if row["expires_at"] <= now() or grant["issuer"] != self.server.settings.issuer or grant["resource"] != self.server.settings.resource:
            return None
        return CodeCredential(row, grant)

    def delete_authorization_code(self, credential):
        self.server.conn.execute(text("UPDATE oauth_codes SET consumed_at=now() WHERE id=:id"), {"id": credential.row["id"]})

    def authenticate_user(self, credential): return credential.grant["user_id"]


class RefreshGrant(RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, token):
        c = self.server.conn
        row = c.execute(text("SELECT * FROM tokens WHERE token_hash=:hash AND kind='refresh'"), {"hash": sha(token)}).mappings().one_or_none()
        if row is None: return None
        grant = active_grant(c, row["grant_id"])
        # Bind the client before replay handling: another client cannot revoke a stolen family's tokens.
        if grant is None or grant["client_id"] != self.request.client.client_id: return None
        row = c.execute(text("SELECT * FROM tokens WHERE id=:id FOR UPDATE"), {"id": row["id"]}).mappings().one()
        if row["consumed_at"] is not None:
            revoke_family(c, row["grant_id"])
            return None
        if row["revoked_at"] or row["expires_at"] <= now() or row["resource"] != self.server.settings.resource or row["issuer"] != self.server.settings.issuer:
            return None
        return TokenCredential(row, grant)

    def authenticate_user(self, credential): return credential.grant["user_id"]

    def revoke_old_credential(self, credential):
        self.server.conn.execute(text("UPDATE tokens SET consumed_at=now() WHERE id=:id"), {"id": credential.row["id"]})


class Revoke(RevocationEndpoint):
    CLIENT_AUTH_METHODS = ["none"]
    def query_token(self, token_string, token_type_hint):
        c = self.server.conn
        row = c.execute(text("SELECT * FROM tokens WHERE token_hash=:hash"), {"hash": sha(token_string)}).mappings().one_or_none()
        if row is None: return None
        grant = c.execute(text("SELECT * FROM oauth_grants WHERE id=:id FOR UPDATE"), {"id": row["grant_id"]}).mappings().one()
        return TokenCredential(row, grant)
    def revoke_token(self, token, request): revoke_family(self.server.conn, token.grant["id"])


class GrantServer(AuthorizationServer):
    def __init__(self, store, conn, *, allow_client_fetch=False):
        super().__init__(scopes_supported=list(SCOPES))
        self.store, self.conn, self.settings = store, conn, store.settings
        self.allow_client_fetch = allow_client_fetch
        self.register_grant(CodeGrant, [S256(required=True)])
        self.register_grant(RefreshGrant)
        self.register_endpoint(Revoke)
        self.register_token_generator("default", self.make_token)
        issuer = self.settings.issuer
        class Issuer(IssuerParameter):
            def get_issuer(self): return issuer
        self.register_extension(Issuer())

    def query_client(self, client_id):
        row = self.store.client(self.conn, client_id, allow_fetch=self.allow_client_fetch)
        return Client(row) if row else None

    def make_token(self, **kwargs):
        result = {"access_token": secrets.token_urlsafe(32), "token_type": "Bearer", "expires_in": self.settings.access_ttl,
                  "scope": kwargs["scope"]}
        if kwargs["include_refresh_token"]: result["refresh_token"] = secrets.token_urlsafe(32)
        return result

    def save_token(self, token, request):
        credential = request.authorization_code if request.payload.grant_type == "authorization_code" else request.refresh_token
        grant = credential.grant
        if grant["issuer"] != self.settings.issuer or grant["resource"] != self.settings.resource:
            raise InvalidGrantError()
        for kind, field, ttl in (("access", "access_token", self.settings.access_ttl), ("refresh", "refresh_token", self.settings.refresh_ttl)):
            if field not in token: continue
            self.conn.execute(text("""INSERT INTO tokens(workspace_id,grant_id,token_hash,kind,issuer,resource,scopes,expires_at,parent_token_id)
                VALUES(:ws,:grant,:hash,:kind,:issuer,:resource,CAST(:scopes AS jsonb),:expiry,:parent)"""),
                {"ws": grant["workspace_id"], "grant": grant["id"], "hash": sha(token[field]), "kind": kind,
                 "issuer": grant["issuer"], "resource": grant["resource"], "scopes": json.dumps(token["scope"].split()),
                 "expiry": now() + timedelta(seconds=ttl),
                 "parent": request.refresh_token.row["id"] if request.payload.grant_type == "refresh_token" else None})

    def create_oauth2_request(self, request): return request
    def handle_response(self, status, body, headers): return OAuthResponse(status, body, headers)
    def send_signal(self, name, *args, **kwargs): pass
