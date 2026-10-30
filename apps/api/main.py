from contextlib import asynccontextmanager
from uuid import UUID, uuid4
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from sqlalchemy import text
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings as MCPAuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, AnyHttpUrl

from goodmcp.database import Database, Principal, NotFound, Forbidden
from goodmcp.storage import Conflict, IntegrityError
from apps.api.registry_api import routes, register_tools
from goodmcp.auth_config import AuthSettings
from goodmcp.version import REVISION, STAGE
from apps.api.mcp_auth import DatabaseVerifier, AccessBoundary, RequestMetadata

settings = AuthSettings.from_env()
database = Database()
verifier = DatabaseVerifier(database, settings)
mcp = MCPServer("goodmcp-hub", version="0.3.0", log_level="WARNING", token_verifier=verifier,
    auth=MCPAuthSettings(issuer_url=AnyHttpUrl(settings.issuer), resource_server_url=AnyHttpUrl(settings.resource),
                        required_scopes=["hub:read"], validate_token_resource=True))


class WorkspaceInfo(BaseModel):
    workspace_id: str
    name: str
    role: str


def workspace_info(token, workspace_id):
    if str(workspace_id) != token.claims["workspace_id"]: raise ValueError("Workspace not found")
    principal = Principal(UUID(token.subject), frozenset(token.scopes))
    with database.tenant(principal, UUID(str(workspace_id))) as tenant:
        name = tenant.connection.execute(text("SELECT name FROM workspaces WHERE id=:id"), {"id": tenant.context.workspace_id}).scalar_one()
        return WorkspaceInfo(workspace_id=str(tenant.context.workspace_id), name=name, role=tenant.context.role)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def hub_get_workspace(workspace_id: Annotated[str, Field(min_length=36, max_length=36)]) -> WorkspaceInfo:
    """Read the workspace authorized by this connection. Requires hub:read; changes no data."""
    token = get_access_token()
    if token is None: raise ValueError("Authentication required")
    return workspace_info(token, UUID(workspace_id))


@asynccontextmanager
async def lifespan(app):
    app.state.db = database
    async with mcp.session_manager.run(): yield
    database.engine.dispose()


app = FastAPI(title="goodmcp local foundation", docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=lifespan)


@app.get("/health/live")
def live(request: Request):
    return {"data": {"status": "alive"}, "request_id": request.state.request_id}


@app.get("/health/ready")
def ready(request: Request):
    try:
        with request.app.state.db.engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if version != REVISION:
                raise RuntimeError("Migration required")
    except Exception:
        # Never include SQL/credentials/internal exception in health responses.
        return JSONResponse({"error": {"code": "runtime_unavailable", "message": "Database or migration unavailable", "retryable": True},
                             "request_id": request.state.request_id}, status_code=503)
    return {"data": {"status": "ready", "stage": STAGE}, "request_id": request.state.request_id}


@app.get("/api/v1/me/workspaces")
def my_workspaces(request: Request):
    token = request.state.access_token
    result = workspace_info(token, token.claims["workspace_id"])
    return {"data": [result.model_dump()], "request_id": request.state.request_id}


app.include_router(routes(database))
register_tools(mcp, database)


async def domain_error(request: Request, exc):
    status, code = (404, "not_found") if isinstance(exc, NotFound) else (403, "forbidden") if isinstance(exc, Forbidden) else (409, "conflict") if isinstance(exc, Conflict) else (422, "invalid_input")
    return JSONResponse({"error": {"code": code, "message": str(exc), "retryable": False},
                         "request_id": getattr(request.state, "request_id", str(uuid4()))}, status_code=status)


for error_type in (NotFound, Forbidden, Conflict, IntegrityError, ValueError):
    app.add_exception_handler(error_type, domain_error)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc):
    return JSONResponse({"error": {"code": "invalid_input", "message": "Invalid request fields", "retryable": False},
                         "request_id": request.state.request_id}, status_code=422)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc):
    return JSONResponse({"error": {"code": "invalid_input" if exc.status_code < 500 else "runtime_unavailable",
                         "message": "Request exceeds body limit" if exc.status_code == 413 else "Request rejected", "retryable": False},
                         "request_id": request.state.request_id}, status_code=exc.status_code)


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def future_authenticated_api(path: str, request: Request):
    return JSONResponse({"error": {"code": "not_found", "message": "This operation is not implemented", "retryable": False},
                         "request_id": request.state.request_id}, status_code=404)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc):
    return JSONResponse({"error": {"code": "internal", "message": "Request failed", "retryable": False},
                         "request_id": getattr(request.state, "request_id", str(uuid4()))}, status_code=500)


app.mount("/", mcp.streamable_http_app(stateless_http=True, json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=[settings.authority], allowed_origins=[settings.origin])))
app.add_middleware(RequestMetadata)
app.add_middleware(AccessBoundary, verifier=verifier, settings=settings)
