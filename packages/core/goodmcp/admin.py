"""Explicit operator-only CLI. Admin secret never mounted into API/worker/tests."""
import argparse
import json
import os
from uuid import uuid4

import psycopg
from psycopg import sql
from .config import database_url, secret
from .fixtures import USER_A, USER_B, VIEWER, WORKSPACE_A, WORKSPACE_B, PROJECT_A, PROJECT_B
from .passwords import password_hash


def connect():
    url = database_url("admin")
    return psycopg.connect(host=url.host, dbname=url.database, user=url.username, password=url.password)


def roles(conn):
    for name, filename in (("hub_migrator", "migrator_password"), ("hub_runtime", "runtime_password"), ("hub_auth", "auth_password")):
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD {}").format(
            sql.Identifier(name), sql.Literal(secret(filename))))
    conn.execute("ALTER DATABASE goodmcp OWNER TO hub_migrator")
    conn.execute("ALTER SCHEMA public OWNER TO hub_migrator")
    conn.execute("REVOKE ALL ON DATABASE goodmcp FROM PUBLIC")
    conn.execute("GRANT CONNECT ON DATABASE goodmcp TO hub_runtime,hub_migrator,hub_auth")
    conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")


def owner(conn):
    email = os.environ.get("HUB_OWNER_EMAIL", "owner@local.invalid").strip().lower()
    old = conn.execute("SELECT id FROM users WHERE email=%s", (email,)).fetchone()
    if old:
        membership = conn.execute("SELECT workspace_id FROM memberships WHERE user_id=%s AND role='owner'", (old[0],)).fetchone()
        if not membership: raise RuntimeError("Owner membership missing")
        return {"created": False, "user_id": str(old[0]), "workspace_id": str(membership[0])}
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        raise RuntimeError("Bootstrap only allowed on an empty identity database")
    user_id, workspace_id = uuid4(), uuid4()
    conn.execute("INSERT INTO users(id,email,password_hash) VALUES (%s,%s,%s)", (user_id, email, password_hash(secret("owner_password"))))
    conn.execute("INSERT INTO workspaces(id,name) VALUES (%s,%s)", (workspace_id, "Khầy — local workspace"))
    conn.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES (%s,%s,'owner')", (workspace_id, user_id))
    return {"created": True, "user_id": str(user_id), "workspace_id": str(workspace_id)}


def fixtures(conn):
    if os.environ.get("HUB_ALLOW_TEST_FIXTURES") != "1":
        raise RuntimeError("Synthetic fixtures are disabled")
    for uid, name in ((USER_A, "a"), (USER_B, "b"), (VIEWER, "viewer")):
        conn.execute("INSERT INTO users(id,email,password_hash) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                     (uid, name + "@fixture.invalid", "!no-login-fixture"))
    for ws, name in ((WORKSPACE_A, "Fixture A"), (WORKSPACE_B, "Fixture B")):
        conn.execute("INSERT INTO workspaces(id,name) VALUES (%s,%s) ON CONFLICT(id) DO NOTHING", (ws, name))
    for uid, ws, role in ((USER_A, WORKSPACE_A, "owner"), (USER_B, WORKSPACE_B, "owner"), (VIEWER, WORKSPACE_A, "viewer")):
        conn.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES (%s,%s,%s) ON CONFLICT(workspace_id,user_id) DO NOTHING", (ws, uid, role))
    for pid, ws, name in ((PROJECT_A, WORKSPACE_A, "Project A"), (PROJECT_B, WORKSPACE_B, "Project B")):
        conn.execute("INSERT INTO projects(id,workspace_id,name) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING", (pid, ws, name))


def inspect_database(conn):
    # Only safe metadata, no password hashes, grants or document contents.
    roles = conn.execute("SELECT rolname,rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname IN ('hub_runtime','hub_migrator') ORDER BY rolname").fetchall()
    tables = conn.execute("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,r.rolname FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname").fetchall()
    return {"roles": roles, "tables": tables, "revision": conn.execute("SELECT version_num FROM alembic_version").fetchone()[0],
            "postgres_version": conn.execute("SHOW server_version").fetchone()[0],
            "users": conn.execute("SELECT count(*) FROM users").fetchone()[0],
            "workspaces": conn.execute("SELECT count(*) FROM workspaces").fetchone()[0]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("roles", "owner", "fixtures", "inspect"))
    args = parser.parse_args()
    with connect() as conn:
        result = {"roles": roles, "owner": owner, "fixtures": fixtures, "inspect": inspect_database}[args.operation](conn)
    print(json.dumps(result or {"status": "ok"}, ensure_ascii=True))


if __name__ == "__main__":
    try: main()
    except Exception:
        # Operator errors must not echo DSNs, SQL PASSWORD literals or hashes.
        print(json.dumps({"error": "operator_command_failed", "message": "Check local DB, role and migration prerequisites"}))
        raise SystemExit(1)
