"""Session-only management routes mounted on the authentication service."""
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from goodmcp.workspace_admin import WorkspaceAdmin


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceInput(Input):
    name: str = Field(min_length=1, max_length=120)


class InvitationInput(Input):
    email: str = Field(min_length=3, max_length=254)
    role: str


class AcceptInput(Input):
    token: str = Field(min_length=30, max_length=128)


class RoleInput(Input):
    role: str


class TransferInput(Input):
    user_id: UUID


class ActiveInput(Input):
    active: bool = Field(strict=True)


def routes(store, authenticate):
    """authenticate(request, write=False) validates session + mutation CSRF.

    The store may be None when routes are installed before app lifespan startup;
    in that case use the initialized request.app.state.store.
    """
    router = APIRouter(prefix="/auth/web")

    def service(request):
        return WorkspaceAdmin(store or request.app.state.store)

    @router.get("/workspaces")
    def workspaces(request: Request):
        session = authenticate(request)
        return {"data": service(request).workspaces(session["user_id"])}

    @router.post("/workspaces", status_code=201)
    def create_workspace(request: Request, data: WorkspaceInput):
        session = authenticate(request, write=True)
        return {"data": service(request).create_workspace(session["user_id"], data.name)}

    @router.patch("/workspaces/{workspace_id}")
    def rename_workspace(request: Request, workspace_id: UUID, data: WorkspaceInput):
        session = authenticate(request, write=True)
        return {"data": service(request).rename_workspace(session["user_id"], workspace_id, data.name)}

    @router.post("/workspaces/{workspace_id}/archive")
    def archive_workspace(request: Request, workspace_id: UUID):
        session = authenticate(request, write=True)
        return {"data": service(request).archive_workspace(session["user_id"], workspace_id)}

    @router.get("/workspaces/{workspace_id}/members")
    def members(request: Request, workspace_id: UUID):
        session = authenticate(request)
        return {"data": service(request).members(session["user_id"], workspace_id)}

    @router.patch("/workspaces/{workspace_id}/members/{user_id}")
    def change_member(request: Request, workspace_id: UUID, user_id: UUID, data: RoleInput):
        session = authenticate(request, write=True)
        return {"data": service(request).change_member(session["user_id"], workspace_id, user_id, data.role)}

    @router.delete("/workspaces/{workspace_id}/members/{user_id}")
    def remove_member(request: Request, workspace_id: UUID, user_id: UUID):
        session = authenticate(request, write=True)
        return {"data": service(request).change_member(session["user_id"], workspace_id, user_id, remove=True)}

    @router.post("/workspaces/{workspace_id}/leave")
    def leave(request: Request, workspace_id: UUID):
        session = authenticate(request, write=True)
        return {"data": service(request).leave(session["user_id"], workspace_id)}

    @router.post("/workspaces/{workspace_id}/transfer")
    def transfer(request: Request, workspace_id: UUID, data: TransferInput):
        session = authenticate(request, write=True)
        return {"data": service(request).transfer(session["user_id"], workspace_id, data.user_id)}

    @router.post("/workspaces/{workspace_id}/invitations", status_code=201)
    def invite(request: Request, workspace_id: UUID, data: InvitationInput):
        session = authenticate(request, write=True)
        return {"data": service(request).invite(session["user_id"], workspace_id, data.email, data.role)}

    @router.get("/workspaces/{workspace_id}/invitations")
    def invitations(request: Request, workspace_id: UUID):
        session = authenticate(request)
        return {"data": service(request).invitations(session["user_id"], workspace_id)}

    @router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}")
    def revoke_invitation(request: Request, workspace_id: UUID, invitation_id: UUID):
        session = authenticate(request, write=True)
        return {"data": service(request).revoke_invitation(session["user_id"], workspace_id, invitation_id)}

    @router.post("/invitations/accept")
    def accept_invitation(request: Request, data: AcceptInput):
        session = authenticate(request, write=True)
        return {"data": service(request).accept_invitation(session["user_id"], data.token,
                                                           email_verified=session.get("email_verified", False))}

    @router.get("/connections")
    def own_connections(request: Request):
        session = authenticate(request)
        return {"data": service(request).connections(session["user_id"])}

    @router.delete("/connections/{grant_id}")
    def revoke_own_connection(request: Request, grant_id: UUID):
        session = authenticate(request, write=True)
        return {"data": service(request).revoke_connection(session["user_id"], grant_id)}

    @router.get("/workspaces/{workspace_id}/connections")
    def connections(request: Request, workspace_id: UUID):
        session = authenticate(request)
        return {"data": service(request).connections(session["user_id"], workspace_id)}

    @router.delete("/workspaces/{workspace_id}/connections/{grant_id}")
    def revoke_connection(request: Request, workspace_id: UUID, grant_id: UUID):
        session = authenticate(request, write=True)
        return {"data": service(request).revoke_connection(session["user_id"], grant_id, workspace_id)}

    @router.get("/workspaces/{workspace_id}/audit")
    def audit(request: Request, workspace_id: UUID):
        session = authenticate(request)
        return {"data": service(request).audit(session["user_id"], workspace_id)}

    @router.get("/platform/users")
    def platform_users(request: Request):
        session = authenticate(request)
        return {"data": service(request).platform_users(session["user_id"])}

    @router.get("/platform/workspaces")
    def platform_workspaces(request: Request):
        session = authenticate(request)
        return {"data": service(request).platform_workspaces(session["user_id"])}

    @router.patch("/platform/users/{user_id}")
    def block_user(request: Request, user_id: UUID, data: ActiveInput):
        session = authenticate(request, write=True)
        return {"data": service(request).block_user(session["user_id"], user_id, data.active)}

    return router
