"""Real isolated-runner acceptance: downgrade a member during Python sleep.

Run after the isolated G9 dispatcher and approved test-probe binding exist:
  docker compose ... run --rm --no-deps -e HUB_ALLOW_TEST_FIXTURES=1 \
    auth_tests python tests/g9_running_revocation.py WORKSPACE_UUID

This process has no Docker socket. It proves a post-create dispatcher heartbeat,
grant revocation, denied future execution and no result publication. The caller
must independently inspect the isolated project's runner containers to prove
physical runner removal, and must label that evidence separately.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import UUID, uuid4

from sqlalchemy import text

from goodmcp.database import Database, Forbidden, Principal
from goodmcp.jobs import Jobs
from goodmcp.oauth_store import AuthStore, sha
from goodmcp.workspace_admin import WorkspaceAdmin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace_id", type=UUID)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    if os.environ.get("HUB_ALLOW_TEST_FIXTURES") != "1" or os.environ.get("HUB_TEST_AUTH") != "1":
        raise RuntimeError("Isolated fixture authorization is required")
    if os.environ.get("HUB_DB_NAME", "goodmcp") != "goodmcp" or not 10 <= args.timeout <= 45:
        raise RuntimeError("Unexpected test database or timeout")

    store, database = AuthStore(), Database(pool_size=2)
    service = WorkspaceAdmin(store)
    checks = []
    start = time.monotonic()

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "passed": True})

    def snapshot(job_id):
        with store.engine.connect() as c:
            return c.execute(text("""SELECT id,state,attempts,started_at,heartbeat_at,finished_at,
                result_artifact_id,error_code,cancel_requested_at FROM jobs WHERE id=:id AND workspace_id=:ws"""),
                {"id": job_id, "ws": args.workspace_id}).mappings().one()

    try:
        with store.engine.begin() as c:
            owner_id = c.execute(text("""SELECT m.user_id FROM memberships m JOIN users u ON u.id=m.user_id AND u.active
                JOIN workspaces w ON w.id=m.workspace_id AND w.archived_at IS NULL
                WHERE m.workspace_id=:ws AND m.role='owner' AND m.active"""), {"ws": args.workspace_id}).scalar_one()
            member_id, grant_id = uuid4(), uuid4()
            client_id, raw_token = "g9-running-" + uuid4().hex, secrets.token_urlsafe(32)
            c.execute(text("""INSERT INTO users(id,email,password_hash,name,email_verified)
                VALUES(:id,:email,'!','G9 isolated running revoke',true)"""),
                {"id": member_id, "email": str(member_id) + "@g9-running.fixture.invalid"})
            c.execute(text("INSERT INTO memberships(workspace_id,user_id,role) VALUES(:ws,:u,'member')"),
                {"ws": args.workspace_id, "u": member_id})
            c.execute(text("""INSERT INTO oauth_clients(client_id,name,redirect_uris,allowed_scopes,source)
                VALUES(:id,'G9 running downgrade test','[\"https://fixture.invalid/callback\"]',
                    '[\"hub:read\",\"hub:write\",\"tools:run\"]','operator')"""), {"id": client_id})
            c.execute(text("""INSERT INTO oauth_grants(id,workspace_id,user_id,client_id,scopes,issuer,resource)
                VALUES(:id,:ws,:u,:client,'[\"hub:read\",\"hub:write\",\"tools:run\"]',:issuer,:resource)"""),
                {"id": grant_id, "ws": args.workspace_id, "u": member_id, "client": client_id,
                    "issuer": store.settings.issuer, "resource": store.settings.resource})
            c.execute(text("""INSERT INTO tokens(workspace_id,grant_id,token_hash,expires_at,issuer,resource,scopes)
                VALUES(:ws,:grant,:hash,now()+interval '1 hour',:issuer,:resource,
                    '[\"hub:read\",\"hub:write\",\"tools:run\"]')"""),
                {"ws": args.workspace_id, "grant": grant_id, "hash": sha(raw_token),
                    "issuer": store.settings.issuer, "resource": store.settings.resource})
        principal = Principal(member_id, frozenset({"hub:read", "hub:write", "tools:run"}))
        with database.tenant(principal, args.workspace_id) as tenant:
            binding = tenant.connection.execute(text("""SELECT b.id FROM tool_bindings b JOIN runtime_releases r
                ON r.workspace_id=b.workspace_id AND r.plugin_version_id=b.plugin_version_id AND r.image_digest=b.image_digest
                JOIN installations i ON i.workspace_id=b.workspace_id AND i.plugin_version_id=b.plugin_version_id AND i.enabled
                WHERE b.workspace_id=:ws AND b.adapter_id='_probe' ORDER BY b.id LIMIT 1"""),
                {"ws": args.workspace_id}).scalar_one()
            job_id = Jobs(tenant, Path(os.environ.get("HUB_STORAGE_ROOT", "/data"))).enqueue(binding, {"kind": "sleep"}, uuid4().hex)["id"]
        running = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            row = snapshot(job_id)
            if row["state"] == "running" and row["heartbeat_at"] and row["started_at"] and row["heartbeat_at"] > row["started_at"]:
                running = row
                break
            if row["state"] in {"succeeded", "failed", "cancelled"}:
                raise AssertionError("Probe terminated before post-create heartbeat")
            time.sleep(0.1)
        check("Python probe reached post-container-create heartbeat before downgrade", running is not None)
        print(json.dumps({"event": "running_before_downgrade", "job_id": str(job_id),
            "attempt": running["attempts"], "elapsed_s": round(time.monotonic() - start, 3)}), flush=True)
        downgraded_at = time.monotonic()
        service.change_member(owner_id, args.workspace_id, member_id, "viewer")
        check("Owner downgraded the running job's actor to viewer", True)
        with store.engine.connect() as c:
            check("Downgrade revoked the original grant", c.execute(text("SELECT revoked_at IS NOT NULL FROM oauth_grants WHERE id=:id"), {"id": grant_id}).scalar_one())
            check("Downgrade revoked the original access token", c.execute(text("SELECT revoked_at IS NOT NULL FROM tokens WHERE token_hash=:hash"), {"hash": sha(raw_token)}).scalar_one())
        with database.engine.connect() as c:
            check("Resource-server verifier rejects the old token", not c.execute(text("SELECT 1 FROM hub_access_identity(:hash,:issuer,:resource)"),
                {"hash": sha(raw_token), "issuer": store.settings.issuer, "resource": store.settings.resource}).first())
        denied = False
        try:
            with database.tenant(principal, args.workspace_id) as tenant:
                Jobs(tenant, Path(os.environ.get("HUB_STORAGE_ROOT", "/data"))).enqueue(binding, {"kind": "sleep"}, uuid4().hex)
        except Forbidden:
            denied = True
        check("The same actor cannot enqueue another Python job as viewer", denied)
        final = None
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            row = snapshot(job_id)
            check_result = row["result_artifact_id"] is None and row["state"] != "succeeded"
            if not check_result:
                raise AssertionError("A result was published after permission loss")
            if row["state"] in {"failed", "cancelled"}:
                final = row
                break
            time.sleep(0.1)
        check("Running job became terminal after downgrade", final is not None)
        check("Permission loss never publishes a successful result", final["result_artifact_id"] is None and final["state"] in {"failed", "cancelled"})
        with database.tenant(Principal(owner_id, frozenset({"hub:read"})), args.workspace_id) as tenant:
            artifact_count = tenant.connection.execute(text("SELECT count(*) FROM artifacts WHERE workspace_id=:ws AND created_by_user_id=:u"),
                {"ws": args.workspace_id, "u": member_id}).scalar_one()
        check("No result artifact was created for the downgraded actor", artifact_count == 0)
        terminal_delay = round(time.monotonic() - downgraded_at, 3)
        return {"passed": True, "scope": "isolated_real_python_runner", "checks": checks,
            "job_id": str(job_id), "workspace_id": str(args.workspace_id), "state": final["state"],
            "error_code": final["error_code"], "attempts": final["attempts"], "terminal_delay_s": terminal_delay,
            "result_artifact_id": None, "new_artifact_count": artifact_count,
            "physical_container_removal": "requires_caller_docker_inspection"}
    finally:
        database.engine.dispose()
        store.engine.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(main()), flush=True)
    except Exception as exc:
        # Assertions are fixed safe labels; don't print SQL/credential values.
        print(json.dumps({"passed": False, "error": type(exc).__name__,
            "check": str(exc) if isinstance(exc, AssertionError) else "running_revocation_harness_failed"}), flush=True)
        sys.exit(1)
