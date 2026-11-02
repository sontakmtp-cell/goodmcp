"""Web-session management operations, using only the issuer database role.

The API's bearer credential cannot invoke this service. Every operation checks
the current account and workspace membership in the transaction that changes it.
"""
from datetime import timedelta
import json
import re
import secrets
from urllib.parse import urlencode
from uuid import UUID, uuid4

from sqlalchemy import text

from .database import Forbidden, NotFound
from .oauth_store import now, sha, revoke_family
from .storage import Conflict


ROLES = frozenset({"owner", "admin", "member", "viewer"})


def clean_name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise ValueError("Tên phải có từ 1 đến 120 ký tự")
    value = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Tên chứa ký tự không hợp lệ")
    return value


def clean_email(value):
    if not isinstance(value, str):
        raise ValueError("Email không hợp lệ")
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value
    ):
        raise ValueError("Email không hợp lệ")
    return value


class WorkspaceAdmin:
    def __init__(self, store):
        self.store = store
        self.engine = store.engine

    def _actor(self, c, user_id):
        actor = c.execute(text("SELECT id,email,name,active,platform_admin FROM users WHERE id=:id AND active FOR SHARE"),
                          {"id": user_id}).mappings().one_or_none()
        if actor is None:
            raise Forbidden("Tài khoản không hoạt động")
        return actor

    def _workspace(self, c, user_id, workspace_id, roles=ROLES, *, archived=False):
        workspace = c.execute(text("SELECT id,name,archived_at FROM workspaces WHERE id=:id FOR UPDATE"),
                              {"id": workspace_id}).mappings().one_or_none()
        member = c.execute(text("SELECT id,user_id,role FROM memberships WHERE workspace_id=:ws AND user_id=:u AND active"),
                           {"ws": workspace_id, "u": user_id}).mappings().one_or_none()
        if workspace is None or member is None or (workspace["archived_at"] is not None and not archived):
            raise NotFound("Không tìm thấy workspace")
        if member["role"] not in roles:
            raise Forbidden("Vai trò hiện tại không được thực hiện thao tác này")
        return {**workspace, "role": member["role"]}

    def _audit(self, c, workspace_id, user_id, action, details=None):
        c.execute(text("""INSERT INTO audit_events(workspace_id,user_id,action,request_id,details)
            VALUES(:ws,:u,:action,:request,CAST(:details AS jsonb))"""),
                  {"ws": workspace_id, "u": user_id, "action": action, "request": uuid4(),
                   "details": json.dumps(details or {}, default=str)})

    def _revoke(self, c, workspace_id, user_id=None):
        params = {"ws": workspace_id, "u": user_id}
        predicate = "workspace_id=:ws" + (" AND user_id=:u" if user_id else "")
        grants = c.execute(text("SELECT id FROM oauth_grants WHERE " + predicate + " AND revoked_at IS NULL FOR UPDATE"), params).scalars().all()
        for grant_id in grants:
            revoke_family(c, grant_id)
        # Running jobs receive a cancellation request; queued jobs become terminal
        # immediately. Dispatchers recheck authorization before result publication.
        c.execute(text("""UPDATE jobs SET cancel_requested_at=COALESCE(cancel_requested_at,now()),
            state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
            finished_at=CASE WHEN state='queued' THEN now() ELSE finished_at END
            WHERE """ + predicate + " AND state IN ('queued','running')"), params)

    def workspaces(self, user_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            return [dict(r) for r in c.execute(text("""SELECT w.id,w.name,w.archived_at,m.role FROM workspaces w
                JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=:u AND m.active
                AND w.archived_at IS NULL ORDER BY w.created_at,w.id"""), {"u": user_id}).mappings()]

    def create_workspace(self, user_id, name):
        name = clean_name(name)
        with self.engine.begin() as c:
            self._actor(c, user_id)
            workspace_id = uuid4()
            c.execute(text("INSERT INTO workspaces(id,name) VALUES(:ws,:name)"), {"ws": workspace_id, "name": name})
            c.execute(text("INSERT INTO memberships(workspace_id,user_id,role) VALUES(:ws,:u,'owner')"),
                      {"ws": workspace_id, "u": user_id})
            self._audit(c, workspace_id, user_id, "workspace.created")
            return {"id": workspace_id, "name": name, "role": "owner", "archived_at": None}

    def rename_workspace(self, user_id, workspace_id, name):
        name = clean_name(name)
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id, {"owner"})
            c.execute(text("UPDATE workspaces SET name=:name WHERE id=:ws"), {"ws": workspace_id, "name": name})
            self._audit(c, workspace_id, user_id, "workspace.renamed", {"name": name})
            return {"id": workspace_id, "name": name}

    def archive_workspace(self, user_id, workspace_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id, {"owner"})
            c.execute(text("UPDATE workspaces SET archived_at=now() WHERE id=:ws"), {"ws": workspace_id})
            self._revoke(c, workspace_id)
            c.execute(text("UPDATE workspace_invitations SET revoked_at=now() WHERE workspace_id=:ws AND accepted_at IS NULL AND revoked_at IS NULL"), {"ws": workspace_id})
            self._audit(c, workspace_id, user_id, "workspace.archived")
            return {"archived": True}

    def members(self, user_id, workspace_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id)
            return [dict(r) for r in c.execute(text("""SELECT m.id,m.user_id,m.role,m.active,u.email,u.name,u.active AS account_active
                FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=:ws AND m.active
                ORDER BY m.created_at,m.id"""), {"ws": workspace_id}).mappings()]

    @staticmethod
    def _manageable(actor_role, target_role, new_role=None):
        if target_role == "owner" or new_role == "owner":
            raise Forbidden("Dùng thao tác chuyển chủ sở hữu")
        if actor_role == "admin" and (target_role not in {"member", "viewer"} or new_role not in {None, "member", "viewer"}):
            raise Forbidden("Admin chỉ quản lý member và viewer")

    def change_member(self, user_id, workspace_id, target_id, role=None, *, remove=False):
        if not remove and role not in ROLES:
            raise ValueError("Vai trò không hợp lệ")
        with self.engine.begin() as c:
            self._actor(c, user_id)
            actor = self._workspace(c, user_id, workspace_id, {"owner", "admin"})
            target = c.execute(text("SELECT role FROM memberships WHERE workspace_id=:ws AND user_id=:u AND active FOR UPDATE"),
                               {"ws": workspace_id, "u": target_id}).scalar_one_or_none()
            if target is None:
                raise NotFound("Không tìm thấy thành viên")
            self._manageable(actor["role"], target, None if remove else role)
            if target_id == user_id:
                raise Forbidden("Dùng thao tác rời workspace để rời nhóm")
            if remove:
                c.execute(text("UPDATE memberships SET active=false WHERE workspace_id=:ws AND user_id=:u"), {"ws": workspace_id, "u": target_id})
            else:
                c.execute(text("UPDATE memberships SET role=:role WHERE workspace_id=:ws AND user_id=:u"), {"ws": workspace_id, "u": target_id, "role": role})
            if remove or target != role:
                self._revoke(c, workspace_id, target_id)
            self._audit(c, workspace_id, user_id, "member.removed" if remove else "member.role_changed", {"user_id": target_id, "role": role})
            return {"user_id": target_id, "active": not remove, "role": target if remove else role}

    def leave(self, user_id, workspace_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id, {"admin", "member", "viewer"})
            self._audit(c, workspace_id, user_id, "member.left")
            c.execute(text("UPDATE memberships SET active=false WHERE workspace_id=:ws AND user_id=:u"), {"ws": workspace_id, "u": user_id})
            self._revoke(c, workspace_id, user_id)
            return {"left": True}

    def transfer(self, user_id, workspace_id, target_id):
        if user_id == target_id:
            raise ValueError("Chọn một thành viên khác làm chủ sở hữu")
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id, {"owner"})
            target = c.execute(text("""SELECT m.role FROM memberships m JOIN users u ON u.id=m.user_id AND u.active
                WHERE m.workspace_id=:ws AND m.user_id=:u AND m.active FOR UPDATE OF m"""), {"ws": workspace_id, "u": target_id}).first()
            if target is None:
                raise NotFound("Chủ mới phải là thành viên đang hoạt động")
            # Demote then promote within one transaction. Deferred DB owner
            # constraint validates the single final owner at commit.
            c.execute(text("UPDATE memberships SET role='admin' WHERE workspace_id=:ws AND user_id=:u"), {"ws": workspace_id, "u": user_id})
            c.execute(text("UPDATE memberships SET role='owner' WHERE workspace_id=:ws AND user_id=:u"), {"ws": workspace_id, "u": target_id})
            self._revoke(c, workspace_id, user_id)
            self._audit(c, workspace_id, user_id, "workspace.owner_transferred", {"user_id": target_id})
            return {"owner_user_id": target_id}

    def invite(self, user_id, workspace_id, email, role):
        email = clean_email(email)
        if role not in {"admin", "member", "viewer"}:
            raise ValueError("Không thể mời trực tiếp vai trò owner")
        with self.engine.begin() as c:
            self._actor(c, user_id)
            actor = self._workspace(c, user_id, workspace_id, {"owner", "admin"})
            self._manageable(actor["role"], role, role)
            if c.execute(text("""SELECT 1 FROM memberships m JOIN users u ON u.id=m.user_id
                WHERE m.workspace_id=:ws AND lower(u.email)=:email AND m.active"""), {"ws": workspace_id, "email": email}).first():
                raise Conflict("Email này đã là thành viên")
            existing = c.execute(text("""SELECT 1 FROM workspace_invitations WHERE workspace_id=:ws AND email=:email
                AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>now()"""), {"ws": workspace_id, "email": email}).first()
            if existing:
                raise Conflict("Email này đã có lời mời còn hiệu lực")
            if self.store.limit(c, "invite:" + str(workspace_id), 50, increment=True, seconds=3600):
                raise Forbidden("Workspace đã đạt giới hạn gửi lời mời, hãy thử lại sau")
            invitation_id, token = uuid4(), secrets.token_urlsafe(32)
            expires_at = now() + timedelta(days=7)
            c.execute(text("""INSERT INTO workspace_invitations(id,workspace_id,email,role,token_hash,created_by,expires_at)
                VALUES(:id,:ws,:email,:role,:hash,:u,:expiry)"""), {"id": invitation_id, "ws": workspace_id, "email": email,
                    "role": role, "hash": sha(token), "u": user_id, "expiry": expires_at})
            url = self.store.settings.base + "/app/invitations?" + urlencode({"token": token})
            c.execute(text("INSERT INTO email_outbox(recipient,subject,body) VALUES(:email,:subject,:body)"),
                      {"email": email, "subject": "Lời mời tham gia " + actor["name"] + " trên GoodMCP",
                       "body": "Bạn được mời vào workspace " + actor["name"] + " với vai trò " + role + ".\n"
                       "Đăng nhập Google bằng đúng email này rồi mở liên kết (hết hạn sau 7 ngày):\n" + url})
            self._audit(c, workspace_id, user_id, "invitation.created", {"invitation_id": invitation_id, "email": email, "role": role})
            return {"id": invitation_id, "email": email, "role": role, "expires_at": expires_at, "delivery": "queued"}

    def invitations(self, user_id, workspace_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id, {"owner", "admin"})
            return [dict(r) for r in c.execute(text("""SELECT id,email,role,expires_at,accepted_at,revoked_at,created_at
                FROM workspace_invitations WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT 100"""), {"ws": workspace_id}).mappings()]

    def revoke_invitation(self, user_id, workspace_id, invitation_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            actor = self._workspace(c, user_id, workspace_id, {"owner", "admin"})
            invitation = c.execute(text("SELECT role,accepted_at FROM workspace_invitations WHERE workspace_id=:ws AND id=:id FOR UPDATE"),
                                   {"ws": workspace_id, "id": invitation_id}).mappings().one_or_none()
            if invitation is None:
                raise NotFound("Không tìm thấy lời mời")
            self._manageable(actor["role"], invitation["role"])
            if invitation["accepted_at"] is not None:
                raise Conflict("Lời mời đã được nhận; hãy quản lý thành viên")
            c.execute(text("UPDATE workspace_invitations SET revoked_at=COALESCE(revoked_at,now()) WHERE id=:id"), {"id": invitation_id})
            self._audit(c, workspace_id, user_id, "invitation.revoked", {"invitation_id": invitation_id})
            return {"revoked": True}

    def accept_invitation(self, user_id, token, *, email_verified=False):
        if not email_verified:
            raise Forbidden("Cần đăng nhập Google bằng email đã được xác minh để nhận lời mời")
        if not isinstance(token, str) or not 30 <= len(token) <= 128:
            raise NotFound("Lời mời không hợp lệ hoặc đã hết hạn")
        with self.engine.begin() as c:
            actor = self._actor(c, user_id)
            # Read ID first, then acquire the same workspace lock used by revoke
            # and archive before locking the invitation: consistent lock ordering.
            workspace_id = c.execute(text("SELECT workspace_id FROM workspace_invitations WHERE token_hash=:hash"), {"hash": sha(token)}).scalar_one_or_none()
            if workspace_id is None:
                raise NotFound("Lời mời không hợp lệ hoặc đã hết hạn")
            workspace = c.execute(text("SELECT id FROM workspaces WHERE id=:id AND archived_at IS NULL FOR UPDATE"), {"id": workspace_id}).first()
            invitation = c.execute(text("""SELECT * FROM workspace_invitations WHERE token_hash=:hash
                AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>now() FOR UPDATE"""), {"hash": sha(token)}).mappings().one_or_none()
            if not workspace or invitation is None:
                raise NotFound("Lời mời không hợp lệ hoặc đã hết hạn")
            if invitation["email"].lower() != actor["email"].lower():
                raise Forbidden("Đăng nhập bằng đúng email được mời")
            inviter = c.execute(text("""SELECT m.role FROM memberships m JOIN users u ON u.id=m.user_id AND u.active
                WHERE m.workspace_id=:ws AND m.user_id=:u AND m.active"""),
                {"ws": workspace_id, "u": invitation["created_by"]}).scalar_one_or_none()
            if inviter not in {"owner", "admin"} or (invitation["role"] == "admin" and inviter != "owner"):
                raise Forbidden("Người mời không còn quyền cấp vai trò này; hãy xin lời mời mới")
            current = c.execute(text("SELECT role,active FROM memberships WHERE workspace_id=:ws AND user_id=:u FOR UPDATE"),
                                {"ws": workspace_id, "u": user_id}).mappings().one_or_none()
            if current and current["active"]:
                raise Conflict("Tài khoản đã là thành viên workspace")
            c.execute(text("""INSERT INTO memberships(workspace_id,user_id,role) VALUES(:ws,:u,:role)
                ON CONFLICT(workspace_id,user_id) DO UPDATE SET active=true,role=EXCLUDED.role"""),
                      {"ws": workspace_id, "u": user_id, "role": invitation["role"]})
            c.execute(text("UPDATE workspace_invitations SET accepted_at=now() WHERE id=:id"), {"id": invitation["id"]})
            self._audit(c, workspace_id, user_id, "invitation.accepted", {"invitation_id": invitation["id"]})
            return {"workspace_id": workspace_id, "role": invitation["role"]}

    def connections(self, user_id, workspace_id=None):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            parameters = {"u": user_id, "ws": workspace_id}
            predicate = "g.user_id=:u"
            if workspace_id is not None:
                workspace = self._workspace(c, user_id, workspace_id)
                predicate = "g.workspace_id=:ws" + ("" if workspace["role"] in {"owner", "admin"} else " AND g.user_id=:u")
            return [dict(r) for r in c.execute(text("""SELECT g.id,g.workspace_id,w.name AS workspace_name,g.user_id,
                u.email AS granted_by,cl.name AS application,g.client_id,g.scopes,g.created_at,g.revoked_at,
                CASE WHEN g.revoked_at IS NOT NULL OR NOT u.active OR NOT m.active OR w.archived_at IS NOT NULL
                    THEN 'revoked' WHEN NOT cl.active THEN 'disabled'
                    WHEN EXISTS(SELECT 1 FROM tokens t WHERE t.grant_id=g.id AND t.revoked_at IS NULL
                        AND t.consumed_at IS NULL AND t.expires_at>now()) THEN 'active' ELSE 'expired' END AS status
                FROM oauth_grants g JOIN oauth_clients cl ON cl.client_id=g.client_id
                JOIN users u ON u.id=g.user_id JOIN workspaces w ON w.id=g.workspace_id
                JOIN memberships m ON m.workspace_id=g.workspace_id AND m.user_id=g.user_id
                WHERE """ + predicate + " ORDER BY g.created_at DESC LIMIT 200"), parameters).mappings()]

    def revoke_connection(self, user_id, grant_id, workspace_id=None):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            grant = c.execute(text("SELECT workspace_id,user_id FROM oauth_grants WHERE id=:id"), {"id": grant_id}).mappings().one_or_none()
            if grant is None or (workspace_id is not None and grant["workspace_id"] != workspace_id):
                raise NotFound("Không tìm thấy kết nối")
            if workspace_id is not None or grant["user_id"] != user_id:
                workspace = self._workspace(c, user_id, grant["workspace_id"])
                if grant["user_id"] != user_id and workspace["role"] not in {"owner", "admin"}:
                    raise Forbidden("Chỉ được thu hồi kết nối của chính mình")
            revoke_family(c, grant_id)
            self._audit(c, grant["workspace_id"], user_id, "connection.revoked", {"grant_id": grant_id})
            return {"revoked": True}

    def audit(self, user_id, workspace_id):
        with self.engine.begin() as c:
            self._actor(c, user_id)
            self._workspace(c, user_id, workspace_id, {"owner", "admin"}, archived=True)
            return [dict(r) for r in c.execute(text("""SELECT a.id,a.user_id,u.email,a.action,a.details,a.created_at FROM audit_events a
                JOIN users u ON u.id=a.user_id WHERE a.workspace_id=:ws ORDER BY a.created_at DESC,a.id LIMIT 100"""), {"ws": workspace_id}).mappings()]

    def platform_users(self, user_id):
        with self.engine.begin() as c:
            if not self._actor(c, user_id)["platform_admin"]:
                raise Forbidden("Cần quyền quản trị nền tảng")
            return [dict(r) for r in c.execute(text("SELECT id,email,name,active,platform_admin,created_at FROM users ORDER BY created_at,id LIMIT 500")).mappings()]

    def platform_workspaces(self, user_id):
        with self.engine.begin() as c:
            if not self._actor(c, user_id)["platform_admin"]:
                raise Forbidden("Cần quyền quản trị nền tảng")
            return [dict(r) for r in c.execute(text("""SELECT w.id,w.name,w.archived_at,w.created_at,
                (SELECT count(*) FROM memberships m WHERE m.workspace_id=w.id AND m.active) AS members,
                (SELECT u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=w.id AND m.active AND m.role='owner') AS owner_email
                FROM workspaces w ORDER BY w.created_at,w.id LIMIT 500""")).mappings()]

    def block_user(self, user_id, target_id, active):
        if not isinstance(active, bool):
            raise ValueError("Trạng thái tài khoản không hợp lệ")
        with self.engine.begin() as c:
            # Serialize platform account changes to protect the final active
            # administrator, including simultaneous requests from two admins.
            c.execute(text("SELECT pg_advisory_xact_lock(470009)"))
            if not self._actor(c, user_id)["platform_admin"]:
                raise Forbidden("Cần quyền quản trị nền tảng")
            if target_id == user_id and not active:
                raise Forbidden("Không thể tự khóa tài khoản quản trị đang dùng")
            target = c.execute(text("SELECT id,platform_admin,active FROM users WHERE id=:id FOR UPDATE"), {"id": target_id}).mappings().one_or_none()
            if target is None:
                raise NotFound("Không tìm thấy tài khoản")
            if not active and target["platform_admin"]:
                count = c.execute(text("SELECT count(*) FROM users WHERE active AND platform_admin")).scalar_one()
                if count <= 1:
                    raise Forbidden("Phải giữ ít nhất một quản trị nền tảng hoạt động")
            c.execute(text("UPDATE users SET active=:active WHERE id=:id"), {"id": target_id, "active": active})
            if not active:
                c.execute(text("DELETE FROM auth_browser_sessions WHERE user_id=:u"), {"u": target_id})
                grants = c.execute(text("SELECT id FROM oauth_grants WHERE user_id=:u AND revoked_at IS NULL FOR UPDATE"), {"u": target_id}).scalars().all()
                for grant_id in grants:
                    revoke_family(c, grant_id)
                c.execute(text("""UPDATE jobs SET cancel_requested_at=COALESCE(cancel_requested_at,now()),
                    state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
                    finished_at=CASE WHEN state='queued' THEN now() ELSE finished_at END
                    WHERE user_id=:u AND state IN ('queued','running')"""), {"u": target_id})
            c.execute(text("""INSERT INTO platform_audit_events(actor_user_id,action,details)
                VALUES(:u,:action,CAST(:details AS jsonb))"""), {"u": user_id,
                    "action": "account.enabled" if active else "account.blocked", "details": json.dumps({"user_id": str(target_id)})})
            return {"id": target_id, "active": active}
