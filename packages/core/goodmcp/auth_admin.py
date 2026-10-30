"""Operator registration and isolated test probes; never an HTTP endpoint."""
import argparse
import json
import os
import base64
import hashlib
import secrets
from pathlib import Path
from uuid import UUID
from .admin import connect
from .oauth_store import sha
from .config import secret

REVOKED_WORKSPACE = UUID("20000000-0000-4000-8000-000000000099")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("fixtures", "negatives", "inspect", "register"))
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    if args.operation in ("fixtures", "negatives") and os.environ.get("HUB_ALLOW_TEST_FIXTURES") != "1":
        raise RuntimeError("Test operations disabled")
    result = {"status": "ok"}
    with connect() as conn:
        if args.operation == "register":
            from .oauth_clients import validate_metadata
            from .auth_config import AuthSettings
            raw = json.loads(args.file.read_text(encoding="utf-8"))
            data = validate_metadata(raw, allow_loopback=not AuthSettings.from_env().secure_cookie)
            client_id = raw["client_id"]
            if not isinstance(client_id, str) or not 1 <= len(client_id) <= 200 or client_id.startswith("https://"):
                raise ValueError("Use a stable non-URL operator client ID")
            conn.execute("""INSERT INTO oauth_clients(client_id,name,redirect_uris,allowed_scopes,source)
                VALUES(%s,%s,%s::jsonb,%s::jsonb,'operator') ON CONFLICT(client_id) DO NOTHING""",
                (client_id, data["name"], json.dumps(data["redirect_uris"]), json.dumps(data["allowed_scopes"])))
            result = {"registered_client_id": client_id}
        elif args.operation == "fixtures":
            owner = conn.execute("SELECT user_id FROM memberships WHERE role='owner' ORDER BY created_at LIMIT 1").fetchone()[0]
            conn.execute("INSERT INTO workspaces(id,name) VALUES(%s,'G2 revoked fixture') ON CONFLICT(id) DO NOTHING", (REVOKED_WORKSPACE,))
            conn.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES(%s,%s,'owner') ON CONFLICT(workspace_id,user_id) DO NOTHING", (REVOKED_WORKSPACE, owner))
            salt = secrets.token_bytes(16)
            digest = hashlib.scrypt(secret("owner_password").encode(), salt=salt, n=16384, r=8, p=1)
            legacy = "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()
            conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (legacy, owner))
            result = {"revoked_workspace_fixture": str(REVOKED_WORKSPACE), "legacy_login_fixture": True}
        elif args.operation == "negatives":
            state = json.loads(Path("/wirestate/state.json").read_text())
            for name in ("expired", "audience", "issuer", "scope"):
                token_hash = sha(state["negative_tokens"][name]["access_token"])
                statement = {
                    "expired": "UPDATE tokens SET expires_at=now()-interval '1 second' WHERE token_hash=%s",
                    "audience": "UPDATE tokens SET resource='https://wrong.invalid/mcp' WHERE token_hash=%s",
                    "issuer": "UPDATE tokens SET issuer='https://wrong.invalid/auth' WHERE token_hash=%s",
                    "scope": "UPDATE tokens SET scopes='[\"projects:read\"]'::jsonb WHERE token_hash=%s",
                }[name]
                assert conn.execute(statement, (token_hash,)).rowcount == 1
            conn.execute("UPDATE memberships SET active=false WHERE workspace_id=%s", (REVOKED_WORKSPACE,))
            result = {"negative_fixtures_applied": True}
        else:
            role = conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='hub_auth'").fetchone()
            assert role == (False, False)
            assert conn.execute("SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE r.rolname='hub_auth'").fetchone()[0] == 0
            rows = conn.execute("SELECT token_hash FROM tokens").fetchall()
            codes = conn.execute("SELECT code_hash FROM oauth_codes").fetchall()
            sessions = conn.execute("SELECT token_hash,csrf_hash FROM auth_browser_sessions").fetchall()
            assert all(len(r[0]) == 64 for r in rows + codes)
            assert all(len(x) == 64 for row in sessions for x in row)
            owner_hash = conn.execute("SELECT password_hash FROM users WHERE email='owner@local.invalid'").fetchone()[0]
            assert owner_hash.startswith("$argon2id$")
            result = {"auth_role_owner_superuser_bypass": False, "tokens_hash_only": True, "codes_sessions_hash_only": True,
                      "owner_argon2id": True, "token_rows": len(rows), "code_rows": len(codes),
                      "refresh_consumed_rows": conn.execute("SELECT count(*) FROM tokens WHERE kind='refresh' AND consumed_at IS NOT NULL").fetchone()[0]}
    print(json.dumps(result))


if __name__ == "__main__":
    try: main()
    except Exception:
        print(json.dumps({"error": "auth_operator_failed"}))
        raise SystemExit(1)
