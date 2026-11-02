"""G9 management acceptance against a real isolated PostgreSQL.

The ordinary runtime test container deliberately has no issuer secret. The G9
verification runner enables these tests with HUB_TEST_AUTH=1 and mounts that
secret only in its isolated test project.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from goodmcp.auth_config import AuthSettings
from goodmcp.database import Database, Forbidden, NotFound, Principal
from goodmcp.oauth_store import AuthStore, now, sha
from goodmcp.storage import Conflict
from goodmcp.workspace_admin import WorkspaceAdmin, clean_email, clean_name


def test_management_input_validation():
    assert clean_name("  Workspace Việt  ") == "Workspace Việt"
    assert clean_email("  EXAMPLE@Example.org ") == "example@example.org"
    for value in (None, "", "a" * 121, "bad\nname"):
        with pytest.raises(ValueError):
            clean_name(value)
    for value in (None, "", "missing-at", "a@b", "bad\r\n@example.org"):
        with pytest.raises(ValueError):
            clean_email(value)


@pytest.fixture
def management():
    if os.environ.get("HUB_TEST_AUTH") != "1":
        pytest.skip("G9 management integration needs isolated issuer test credential")
    store = AuthStore(AuthSettings.from_env())
    service = WorkspaceAdmin(store)
    ids = {name: uuid4() for name in ("owner", "admin", "member", "viewer", "outsider", "platform")}
    with store.engine.begin() as c:
        for name, uid in ids.items():
            c.execute(text("""INSERT INTO users(id,email,password_hash,name,email_verified,platform_admin)
                VALUES(:id,:email,'!',:name,true,:platform)"""), {"id": uid, "email": str(uid) + "@g9.fixture.invalid",
                    "name": name, "platform": name == "platform"})
    workspace = service.create_workspace(ids["owner"], "G9 isolated workspace")
    other = service.create_workspace(ids["outsider"], "G9 other workspace")
    with store.engine.begin() as c:
        for role in ("admin", "member", "viewer"):
            c.execute(text("INSERT INTO memberships(workspace_id,user_id,role) VALUES(:ws,:u,:role)"),
                      {"ws": workspace["id"], "u": ids[role], "role": role})
    yield SimpleNamespace(store=store, service=service, users=ids, ws=workspace["id"], other=other["id"])
    store.engine.dispose()


def invitation_token(m, email):
    with m.store.engine.connect() as c:
        body = c.execute(text("SELECT body FROM email_outbox WHERE recipient=:email ORDER BY created_at DESC LIMIT 1"), {"email": email}).scalar_one()
    return parse_qs(urlsplit(body.splitlines()[-1]).query)["token"][0]


def email_of(m, name):
    return str(m.users[name]) + "@g9.fixture.invalid"


def grant(m, user="member"):
    client_id, grant_id, raw = "g9-" + uuid4().hex, uuid4(), "g9-token-" + uuid4().hex
    with m.store.engine.begin() as c:
        c.execute(text("""INSERT INTO oauth_clients(client_id,name,redirect_uris,allowed_scopes,source)
            VALUES(:id,'G9 test app','[\"https://fixture.invalid/callback\"]','[\"hub:read\",\"hub:write\"]','operator')"""), {"id": client_id})
        c.execute(text("""INSERT INTO oauth_grants(id,workspace_id,user_id,client_id,scopes,issuer,resource)
            VALUES(:id,:ws,:u,:client,'[\"hub:read\",\"hub:write\"]',:issuer,:resource)"""),
                  {"id": grant_id, "ws": m.ws, "u": m.users[user], "client": client_id,
                   "issuer": m.store.settings.issuer, "resource": m.store.settings.resource})
        c.execute(text("""INSERT INTO tokens(workspace_id,grant_id,token_hash,expires_at,issuer,resource,scopes)
            VALUES(:ws,:grant,:hash,now()+interval '1 hour',:issuer,:resource,'[\"hub:read\",\"hub:write\"]')"""),
                  {"ws": m.ws, "grant": grant_id, "hash": sha(raw), "issuer": m.store.settings.issuer, "resource": m.store.settings.resource})
    return grant_id, raw


def test_workspace_roles_and_cross_workspace_access(management):
    m = management
    assert m.service.workspaces(m.users["member"])[0]["role"] == "member"
    assert {r["role"] for r in m.service.members(m.users["viewer"], m.ws)} == {"owner", "admin", "member", "viewer"}
    with pytest.raises(NotFound):
        m.service.members(m.users["outsider"], m.ws)
    for role in ("admin", "member", "viewer"):
        with pytest.raises(Forbidden):
            m.service.rename_workspace(m.users[role], m.ws, "forged")
        with pytest.raises(Forbidden):
            m.service.archive_workspace(m.users[role], m.ws)
    assert m.service.rename_workspace(m.users["owner"], m.ws, "Renamed")["name"] == "Renamed"
    with pytest.raises(Forbidden):
        m.service.change_member(m.users["admin"], m.ws, m.users["owner"], "viewer")
    with pytest.raises(Forbidden):
        m.service.change_member(m.users["admin"], m.ws, m.users["member"], "admin")
    assert m.service.change_member(m.users["admin"], m.ws, m.users["member"], "viewer")["role"] == "viewer"
    with pytest.raises(Forbidden):
        m.service.leave(m.users["owner"], m.ws)
    assert m.service.leave(m.users["viewer"], m.ws)["left"]
    with pytest.raises(NotFound):
        m.service.members(m.users["viewer"], m.ws)


def test_invitation_verified_email_one_use_and_hashed_token(management):
    m = management
    email = email_of(m, "outsider")
    invitation = m.service.invite(m.users["owner"], m.ws, email.upper(), "member")
    assert invitation["delivery"] == "queued" and "token" not in invitation
    assert timedelta(days=6, hours=23) < invitation["expires_at"] - now() <= timedelta(days=7)
    token = invitation_token(m, email)
    with m.store.engine.connect() as c:
        assert c.execute(text("SELECT token_hash FROM workspace_invitations WHERE id=:id"), {"id": invitation["id"]}).scalar_one() == sha(token)
    with pytest.raises(Conflict):
        m.service.invite(m.users["owner"], m.ws, email, "viewer")
    with pytest.raises(Forbidden):
        m.service.accept_invitation(m.users["outsider"], token, email_verified=False)
    with pytest.raises(Forbidden):
        m.service.accept_invitation(m.users["viewer"], token, email_verified=True)
    accepted = m.service.accept_invitation(m.users["outsider"], token, email_verified=True)
    assert accepted == {"workspace_id": m.ws, "role": "member"}
    with pytest.raises(NotFound):
        m.service.accept_invitation(m.users["outsider"], token, email_verified=True)
    assert len(m.service.workspaces(m.users["outsider"])) == 2


def test_expired_revoked_invitations_and_admin_boundaries(management):
    m = management
    email = email_of(m, "outsider")
    with pytest.raises(Forbidden):
        m.service.invite(m.users["admin"], m.ws, email, "admin")
    invitation = m.service.invite(m.users["owner"], m.ws, email, "admin")
    token = invitation_token(m, email)
    with pytest.raises(Forbidden):
        m.service.revoke_invitation(m.users["admin"], m.ws, invitation["id"])
    m.service.revoke_invitation(m.users["owner"], m.ws, invitation["id"])
    with pytest.raises(NotFound):
        m.service.accept_invitation(m.users["outsider"], token, email_verified=True)
    invitation = m.service.invite(m.users["admin"], m.ws, email, "viewer")
    token = invitation_token(m, email)
    with m.store.engine.begin() as c:
        c.execute(text("UPDATE workspace_invitations SET expires_at=now()-interval '1 second' WHERE id=:id"), {"id": invitation["id"]})
    with pytest.raises(NotFound):
        m.service.accept_invitation(m.users["outsider"], token, email_verified=True)


def test_transfer_is_atomic_under_competing_requests(management):
    m = management
    def transfer(role):
        try:
            return m.service.transfer(m.users["owner"], m.ws, m.users[role])
        except Forbidden:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(transfer, ("admin", "member")))
    assert sum(r is not None for r in results) == 1
    with m.store.engine.connect() as c:
        owners = c.execute(text("SELECT user_id FROM memberships WHERE workspace_id=:ws AND role='owner' AND active"), {"ws": m.ws}).scalars().all()
    assert len(owners) == 1 and owners[0] != m.users["owner"]
    with pytest.raises(DBAPIError):
        with m.store.engine.begin() as c:
            c.execute(text("UPDATE memberships SET active=false WHERE workspace_id=:ws AND role='owner'"), {"ws": m.ws})


def test_downgrade_revokes_tokens_and_cancels_queued_jobs(management):
    m = management
    grant_id, raw = grant(m)
    job_id = uuid4()
    db = Database(pool_size=1)
    try:
        with db.tenant(Principal(m.users["member"], frozenset({"hub:read", "hub:write", "tools:run"})), m.ws) as t:
            t.connection.execute(text("""INSERT INTO jobs(id,workspace_id,user_id,type,operation,input_hash,idempotency_key,deadline_at)
                VALUES(:id,:ws,:u,'finance_light','g9-test',:hash,:key,now()+interval '1 hour')"""),
                                 {"id": job_id, "ws": m.ws, "u": m.users["member"], "hash": "a" * 64, "key": uuid4().hex})
    finally:
        db.engine.dispose()
    m.service.change_member(m.users["owner"], m.ws, m.users["member"], "viewer")
    with m.store.engine.connect() as c:
        assert c.execute(text("SELECT revoked_at IS NOT NULL FROM oauth_grants WHERE id=:id"), {"id": grant_id}).scalar_one()
        assert c.execute(text("SELECT revoked_at IS NOT NULL FROM tokens WHERE token_hash=:hash"), {"hash": sha(raw)}).scalar_one()
        assert c.execute(text("SELECT state,cancel_requested_at IS NOT NULL FROM jobs WHERE id=:id"), {"id": job_id}).one() == ("cancelled", True)


def test_connections_owner_admin_and_self_only(management):
    m = management
    member_grant, _ = grant(m, "member")
    owner_grant, _ = grant(m, "owner")
    assert len(m.service.connections(m.users["owner"], m.ws)) == 2
    assert len(m.service.connections(m.users["member"], m.ws)) == 1
    assert m.service.connections(m.users["viewer"], m.ws) == []
    with pytest.raises(Forbidden):
        m.service.revoke_connection(m.users["member"], owner_grant)
    with pytest.raises(NotFound):
        m.service.revoke_connection(m.users["outsider"], member_grant)
    assert m.service.revoke_connection(m.users["admin"], member_grant, m.ws)["revoked"]
    assert m.service.revoke_connection(m.users["owner"], owner_grant)["revoked"]
    assert all(r["status"] == "revoked" for r in m.service.connections(m.users["owner"], m.ws))
    with pytest.raises(Forbidden):
        m.service.audit(m.users["member"], m.ws)
    assert any(r["action"] == "connection.revoked" for r in m.service.audit(m.users["owner"], m.ws))


def test_platform_is_separate_from_workspace_owner_and_blocks_sessions(management):
    m = management
    for method in (m.service.platform_users, m.service.platform_workspaces):
        with pytest.raises(Forbidden):
            method(m.users["owner"])
    with pytest.raises(Forbidden):
        m.service.block_user(m.users["owner"], m.users["member"], False)
    grant_id, raw = grant(m)
    with m.store.engine.begin() as c:
        cookie, _ = m.store.new_session(c, m.users["member"])
    assert m.service.block_user(m.users["platform"], m.users["member"], False)["active"] is False
    with m.store.engine.connect() as c:
        assert m.store.session(c, cookie) is None
        assert c.execute(text("SELECT revoked_at IS NOT NULL FROM oauth_grants WHERE id=:id"), {"id": grant_id}).scalar_one()
        assert c.execute(text("SELECT revoked_at IS NOT NULL FROM tokens WHERE token_hash=:hash"), {"hash": sha(raw)}).scalar_one()
    with pytest.raises(Forbidden):
        m.service.workspaces(m.users["member"])
    with pytest.raises(Forbidden):
        m.service.block_user(m.users["platform"], m.users["platform"], False)
    assert m.service.block_user(m.users["platform"], m.users["member"], True)["active"] is True
    assert m.service.platform_workspaces(m.users["platform"])


def test_archiving_keeps_data_and_owner_but_denies_workspace_use(management):
    m = management
    grant_id, _ = grant(m)
    m.service.archive_workspace(m.users["owner"], m.ws)
    assert m.service.workspaces(m.users["owner"]) == []
    with pytest.raises(NotFound):
        m.service.members(m.users["owner"], m.ws)
    with m.store.engine.connect() as c:
        assert c.execute(text("SELECT archived_at IS NOT NULL FROM workspaces WHERE id=:ws"), {"ws": m.ws}).scalar_one()
        assert c.execute(text("SELECT count(*) FROM memberships WHERE workspace_id=:ws AND role='owner' AND active"), {"ws": m.ws}).scalar_one() == 1
        assert c.execute(text("SELECT revoked_at IS NOT NULL FROM oauth_grants WHERE id=:id"), {"id": grant_id}).scalar_one()


def test_member_updates_shared_project_without_becoming_its_lead(management, storage_root):
    from goodmcp.workflows import Workflows
    from test_workflows import opc_zip
    from test_registry import publish
    m = management
    scopes = frozenset({'hub:read','hub:write','projects:read','projects:write'})
    db = Database(pool_size=1)
    try:
        with db.tenant(Principal(m.users['owner'], scopes), m.ws) as t:
            w = Workflows(t, storage_root)
            version = publish(w, opc_zip())
            install = w.set_installation(version, True, 0)
            project = w.open_project({'installation_id': str(install['id']), 'name': 'Shared G9 project', 'idempotency_key': uuid4().hex})
        with db.tenant(Principal(m.users['member'], scopes), m.ws) as t:
            w = Workflows(t, storage_root)
            result = w.save_artifact(project['id'], {'expected_revision': 0, 'idempotency_key': uuid4().hex,
                'logical_path': 'opc-doc/outputs/01-resource-audit/member.md', 'content': 'Member contribution'})
            assert result['revision'] == 1
            assert w.read_project(project['id'])['lead_user_id'] == m.users['owner']
        with db.tenant(Principal(m.users['viewer'], scopes), m.ws) as t:
            with pytest.raises(Forbidden):
                Workflows(t, storage_root).project(project['id'], write=True)
    finally:
        db.engine.dispose()
