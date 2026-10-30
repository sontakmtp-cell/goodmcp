import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from goodmcp.database import Forbidden, NotFound, Principal
from goodmcp.fixtures import USER_A, USER_B, WORKSPACE_A, WORKSPACE_B, PROJECT_A, PROJECT_B
from goodmcp.storage import ArtifactStore, IntegrityError, Conflict

PRIVATE_TABLES = ["plugin_packages", "plugin_versions", "installations", "skills", "agents", "resources", "tool_bindings",
                  "projects", "artifacts", "stage_commits", "jobs", "job_attempts", "audit_events", "connections", "oauth_grants", "tokens", "host_profiles"]


def sqlstate(error): return error.value.orig.sqlstate


def test_real_postgres18_runtime_has_no_admin_privileges(db):
    with db.engine.connect() as c:
        assert c.execute(text("SHOW server_version_num")).scalar_one().startswith("18")
        role = c.execute(text("SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user")).one()
        assert role == ("hub_runtime", False, False, False, False)
        assert c.execute(text("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)")).scalar_one() == 0
        assert not c.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one()
        assert not c.execute(text("SELECT has_table_privilege(current_user,'memberships','INSERT')")).scalar_one()
        assert not c.execute(text("SELECT has_table_privilege(current_user,'projects','TRUNCATE')")).scalar_one()
        assert not c.execute(text("SELECT has_column_privilege(current_user,'users','password_hash','SELECT')")).scalar_one()


@pytest.mark.parametrize("table", ["users", "workspaces", "memberships", *PRIVATE_TABLES])
def test_every_private_table_forces_rls_and_migration_owner(db, table):
    with db.engine.connect() as c:
        row = c.execute(text("SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE c.oid=CAST(:t AS regclass)"), {"t": table}).one()
        assert row == (True, True, "hub_migrator")


@pytest.mark.parametrize("table", PRIVATE_TABLES)
def test_contextless_select_is_deny_by_default(db, table):
    with db.engine.connect() as c:
        assert c.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0


def test_missing_context_insert_denied(db):
    with pytest.raises(DBAPIError) as error:
        with db.engine.begin() as c:
            c.execute(text("INSERT INTO projects(workspace_id,name) VALUES (:w,'forged')"), {"w": WORKSPACE_A})
    assert sqlstate(error) == "42501"


def test_workspace_selection_requires_membership(db, a, b):
    assert [row["id"] for row in db.list_workspaces(a)] == [WORKSPACE_A]
    assert [row["id"] for row in db.list_workspaces(b)] == [WORKSPACE_B]
    with pytest.raises(NotFound):
        with db.tenant(a, WORKSPACE_B): pass
    with pytest.raises(Forbidden):
        with db.tenant(Principal(USER_A, frozenset()), WORKSPACE_A): pass


def test_a_cannot_select_update_delete_b_or_forge_workspace(db, a):
    with db.tenant(a, WORKSPACE_A) as t:
        c = t.connection
        assert c.execute(text("SELECT name FROM projects WHERE id=:p"), {"p": PROJECT_A}).scalar_one() == "Project A"
        assert c.execute(text("SELECT id FROM projects WHERE id=:p"), {"p": PROJECT_B}).first() is None
        assert c.execute(text("UPDATE projects SET name='forged' WHERE id=:p"), {"p": PROJECT_B}).rowcount == 0
        assert c.execute(text("DELETE FROM projects WHERE id=:p"), {"p": PROJECT_B}).rowcount == 0
        c.execute(text("SELECT set_config('app.workspace_id',:w,true)"), {"w": str(WORKSPACE_B)})
        assert c.execute(text("SELECT count(*) FROM projects")).scalar_one() == 0


def test_with_check_blocks_inserting_b_and_moving_a_to_b(db, a):
    for statement in ("INSERT INTO projects(workspace_id,name) VALUES (:w,'forged')",
                      "UPDATE projects SET workspace_id=:w WHERE id=:p"):
        with pytest.raises(DBAPIError) as error:
            with db.tenant(a, WORKSPACE_A) as t:
                t.connection.execute(text(statement), {"w": WORKSPACE_B, "p": PROJECT_A})
        assert sqlstate(error) == "42501"


def test_pool_transaction_context_cleared_after_commit_and_rollback(db, a, b):
    pids = []
    with db.tenant(a, WORKSPACE_A) as t:
        pids.append(t.connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
        assert t.connection.execute(text("SELECT id FROM projects")).scalars().all() == [PROJECT_A]
    with pytest.raises(RuntimeError):
        with db.tenant(b, WORKSPACE_B) as t:
            pids.append(t.connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
            assert t.connection.execute(text("SELECT id FROM projects")).scalars().all() == [PROJECT_B]
            raise RuntimeError("Force transaction rollback")
    with db.engine.connect() as c:
        pids.append(c.execute(text("SELECT pg_backend_pid()")).scalar_one())
        assert c.execute(text("SELECT count(*) FROM projects")).scalar_one() == 0
        assert c.execute(text("SELECT NULLIF(current_setting('app.user_id',true),''),NULLIF(current_setting('app.workspace_id',true),'')")).one() == (None, None)
    assert len(set(pids)) == 1, "Must test actual reuse of the same PostgreSQL connection"


def test_cross_tenant_composite_foreign_key(db, a, storage_root):
    with pytest.raises(DBAPIError) as error:
        with db.tenant(a, WORKSPACE_A) as t:
            ArtifactStore(storage_root, t).put([b"no-cross-tenant-parent"], "text/plain", max_bytes=100, project_id=PROJECT_B)
    assert sqlstate(error) == "23503"


def test_viewer_read_allowed_but_core_and_database_write_denied(db, viewer, storage_root):
    with db.tenant(viewer, WORKSPACE_A) as t:
        assert t.connection.execute(text("SELECT name FROM projects WHERE id=:p"), {"p": PROJECT_A}).scalar_one() == "Project A"
        with pytest.raises(Forbidden): ArtifactStore(storage_root, t).put([b"denied"], "text/plain", max_bytes=10)
    with pytest.raises(DBAPIError) as error:
        with db.tenant(viewer, WORKSPACE_A) as t:
            t.connection.execute(text("INSERT INTO projects(workspace_id,name) VALUES (:w,'denied')"), {"w": WORKSPACE_A})
    assert sqlstate(error) == "42501"


def test_read_scope_cannot_write_store(db, storage_root):
    read_only = Principal(USER_A, frozenset({"hub:read"}))
    with db.tenant(read_only, WORKSPACE_A) as t:
        with pytest.raises(Forbidden): ArtifactStore(storage_root, t).put([b"denied"], "text/plain", max_bytes=10)


def test_file_put_get_stream_and_no_cross_workspace_handle(db, a, b, storage_root):
    data = b"first chunk:" + os.urandom(2048)
    with db.tenant(a, WORKSPACE_A) as t:
        store = ArtifactStore(storage_root, t)
        item = store.put([data[:100], data[100:]], "application/octet-stream", max_bytes=len(data), expected_sha256=hashlib.sha256(data).hexdigest())
        assert item.sha256 == hashlib.sha256(data).hexdigest() and item.bytes == len(data)
        assert store.get(item.id).id == item.id
        assert b"".join(store.stream(item.id)) == data
        assert b"".join(store.stream(item.id, (2, 8))) == data[2:8]
        with pytest.raises(ValueError): list(store.stream(item.id, (-1, 8)))
        with pytest.raises(ValueError): list(store.stream(item.id, (0, len(data) + 1)))
    with db.tenant(b, WORKSPACE_B) as t:
        store = ArtifactStore(storage_root, t)
        for action in (lambda: store.get(item.id), lambda: list(store.stream(item.id)),
                       lambda: store.delete(item.id, expected_revision=1)):
            with pytest.raises(NotFound): action()


def test_oversize_bad_checksum_and_empty_file(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        store = ArtifactStore(storage_root, t)
        before = t.connection.execute(text("SELECT count(*) FROM artifacts")).scalar_one()
        with pytest.raises(ValueError): store.put([b"too large"], "text/plain", max_bytes=1)
        with pytest.raises(IntegrityError): store.put([b"bad hash"], "text/plain", max_bytes=100, expected_sha256="a" * 64)
        assert t.connection.execute(text("SELECT count(*) FROM artifacts")).scalar_one() == before
        empty = store.put([], "text/plain", max_bytes=0)
        assert b"".join(store.stream(empty.id)) == b""


def test_traversal_invalid_uuid_and_metadata_namespace_poisoning(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        store = ArtifactStore(storage_root, t)
        with pytest.raises(ValueError): store.get("../../another-workspace")
        with pytest.raises(IntegrityError):
            with store._directory(("..",)): pass
        item = store.put([b"namespace-fixture"], "text/plain", max_bytes=100)
        t.connection.execute(text("UPDATE artifacts SET storage_key=:key WHERE id=:id"),
                             {"key": f"workspaces/{WORKSPACE_B}/blobs/{item.sha256}", "id": item.id})
        with pytest.raises(IntegrityError): list(store.stream(item.id))
        t.connection.execute(text("UPDATE artifacts SET storage_key=:key WHERE id=:id"),
                             {"key": "../../outside", "id": item.id})
        with pytest.raises(IntegrityError): list(store.stream(item.id))


def test_symlink_blob_cannot_escape_root(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        store = ArtifactStore(storage_root, t)
        item = store.put([os.urandom(100)], "application/octet-stream", max_bytes=100)
        path = storage_root / "workspaces" / str(WORKSPACE_A) / "blobs" / item.sha256
        path.unlink()
        path.symlink_to("/etc/passwd")
        try:
            with pytest.raises(IntegrityError): list(store.stream(item.id))
        finally: path.unlink()


def test_symlink_directory_refused(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        target = storage_root / ("symlink-" + uuid4().hex)
        target.symlink_to("/tmp", target_is_directory=True)
        try:
            with pytest.raises(IntegrityError):
                with ArtifactStore(storage_root, t)._directory((target.name,), create=True): pass
        finally: target.unlink()


def test_delete_requires_revision_and_preserves_blob(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        store = ArtifactStore(storage_root, t)
        item = store.put([os.urandom(20)], "application/octet-stream", max_bytes=20)
        with pytest.raises(Conflict): store.delete(item.id, expected_revision=99)
        assert store.delete(item.id, expected_revision=1)["tombstoned"]
        with pytest.raises(NotFound): store.get(item.id)
        assert (storage_root / "workspaces" / str(WORKSPACE_A) / "blobs" / item.sha256).is_file()
        pinned = store.put([os.urandom(20)], "application/octet-stream", max_bytes=20, project_id=PROJECT_A)
        with pytest.raises(Conflict): store.delete(pinned.id, expected_revision=1)


def test_cross_tenant_job_parent_and_idempotency_namespace(db, a, b):
    key = "test-" + uuid4().hex
    query = text("""INSERT INTO jobs(workspace_id,user_id,project_id,type,operation,input_hash,idempotency_key,deadline_at)
        VALUES(:ws,:user,:project,'fixture','test',:hash,:key,now()+interval '1 hour')""")
    with pytest.raises(DBAPIError) as error:
        with db.tenant(a, WORKSPACE_A) as t:
            t.connection.execute(query, {"ws": WORKSPACE_A, "user": USER_A, "project": PROJECT_B, "hash": "a"*64, "key": key})
    assert sqlstate(error) == "23503"
    for principal, ws, user, project in ((a, WORKSPACE_A, USER_A, PROJECT_A), (b, WORKSPACE_B, USER_B, PROJECT_B)):
        with db.tenant(principal, ws) as t:
            t.connection.execute(query, {"ws": ws, "user": user, "project": project, "hash": "a"*64, "key": key})
            assert t.connection.execute(text("SELECT count(*) FROM jobs WHERE idempotency_key=:k"), {"k": key}).scalar_one() == 1
    with pytest.raises(DBAPIError) as error:
        with db.tenant(a, WORKSPACE_A) as t:
            t.connection.execute(query, {"ws": WORKSPACE_A, "user": USER_A, "project": PROJECT_A, "hash": "b"*64, "key": key})
    assert sqlstate(error) == "23505"


def test_runtime_process_has_only_runtime_secret_and_no_host_control():
    assert os.getuid() == 10001
    assert sorted(p.name for p in Path("/run/secrets").iterdir()) == ["runtime_password"]
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("/plugins").exists()


def test_health_and_all_business_routes_fail_closed_even_with_forged_headers():
    with httpx.Client(base_url="http://api:8000") as client:
        for path in ("/health/live", "/health/ready"):
            r = client.get(path)
            assert r.status_code == 200 and r.json()["request_id"] == r.headers["x-request-id"]
            assert "password" not in r.text.lower() and "/run/" not in r.text
        for method, path in (("GET", "/api/v1/me/workspaces"), ("POST", "/api/v1/workspaces/forged/invocations")):
            r = client.request(method, path, headers={"X-User-ID": str(USER_A), "X-Workspace-ID": str(WORKSPACE_A), "Authorization": "Bearer arbitrary"})
            assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
