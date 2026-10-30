from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from goodmcp.database import Database

REVISION = "0001_g1"


@asynccontextmanager
async def lifespan(app):
    app.state.db = Database()
    yield
    app.state.db.engine.dispose()


app = FastAPI(title="goodmcp local foundation", docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def request_id(request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    return response


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
    return {"data": {"status": "ready", "stage": "G1"}, "request_id": request.state.request_id}


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def future_authenticated_api(path: str, request: Request):
    return JSONResponse({"error": {"code": "unauthenticated", "message": "Authentication is implemented in G2", "retryable": False},
                         "request_id": request.state.request_id}, status_code=401)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc):
    return JSONResponse({"error": {"code": "internal", "message": "Request failed", "retryable": False},
                         "request_id": getattr(request.state, "request_id", str(uuid4()))}, status_code=500)
