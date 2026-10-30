from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text

from .config import database_url


class NotFound(Exception):
    """Missing object or object inaccessible to the current tenant."""


class Forbidden(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    """INTERNAL verified identity. G2 will construct it after token/session checks.

    No G1 HTTP route accepts this from a caller or from X-User/X-Workspace headers.
    """
    user_id: UUID
    scopes: frozenset[str]


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    workspace_id: UUID
    membership_id: UUID
    role: str
    scopes: frozenset[str]
    request_id: UUID

    def require_write(self):
        if self.role not in ("owner", "admin", "member") or "hub:write" not in self.scopes:
            raise Forbidden("Write permission required")


@dataclass
class TenantTransaction:
    connection: object
    context: TenantContext


class Database:
    def __init__(self, url=None, *, pool_size=5):
        self.engine = create_engine(url or database_url(), pool_size=pool_size, max_overflow=0,
                                    pool_pre_ping=True, hide_parameters=True, connect_args={"connect_timeout": 3})

    @contextmanager
    def tenant(self, principal: Principal, workspace_id: UUID):
        if "hub:read" not in principal.scopes:
            raise Forbidden("Read permission required")
        with self.engine.begin() as conn:
            # true = transaction local. Rollback/commit removes both contexts on pool reuse.
            conn.execute(text("SELECT set_config('app.user_id', :value, true)"), {"value": str(principal.user_id)})
            member = conn.execute(text("SELECT id, role FROM memberships WHERE user_id=:user AND workspace_id=:ws AND active"),
                                  {"user": principal.user_id, "ws": workspace_id}).mappings().one_or_none()
            if member is None:
                raise NotFound("Workspace not found")
            conn.execute(text("SELECT set_config('app.workspace_id', :value, true)"), {"value": str(workspace_id)})
            ctx = TenantContext(principal.user_id, workspace_id, member["id"], member["role"], principal.scopes, uuid4())
            yield TenantTransaction(conn, ctx)

    def list_workspaces(self, principal: Principal):
        if "hub:read" not in principal.scopes:
            raise Forbidden("Read permission required")
        with self.engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.user_id', :value, true)"), {"value": str(principal.user_id)})
            return conn.execute(text("SELECT w.id,w.name,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=:u AND m.active ORDER BY w.id"),
                                {"u": principal.user_id}).mappings().all()
