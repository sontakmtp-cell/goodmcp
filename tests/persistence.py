"""Separate before/after container recreation probe against persistent DB + blob volume."""
import json
from pathlib import Path
import sys
from sqlalchemy import text
from goodmcp.database import Database, Principal
from goodmcp.fixtures import USER_A, WORKSPACE_A, PROJECT_A
from goodmcp.storage import ArtifactStore

db = Database(pool_size=1)
root = Path("/data")
marker = root / "g1-persistence-marker.json"
principal = Principal(USER_A, frozenset({"hub:read", "hub:write"}))
if sys.argv[1] == "seed":
    with db.tenant(principal, WORKSPACE_A) as t:
        item = ArtifactStore(root, t).put([b"G1 real volume persistence"], "text/plain", max_bytes=100, project_id=PROJECT_A)
        t.connection.execute(text("UPDATE projects SET state=CAST(:state AS jsonb) WHERE id=:id"),
                             {"state": json.dumps({"persisted": str(item.id)}), "id": PROJECT_A})
    marker.write_text(json.dumps({"artifact_id": str(item.id)}), encoding="utf-8")
    print(json.dumps({"seeded": True, "artifact_id": str(item.id), "sha256": item.sha256}))
elif sys.argv[1] == "check":
    record = json.loads(marker.read_text(encoding="utf-8"))
    with db.tenant(principal, WORKSPACE_A) as t:
        state = t.connection.execute(text("SELECT state FROM projects WHERE id=:id"), {"id": PROJECT_A}).scalar_one()
        assert state["persisted"] == record["artifact_id"]
        data = b"".join(ArtifactStore(root, t).stream(record["artifact_id"]))
        assert data == b"G1 real volume persistence"
    print(json.dumps({"persisted_after_recreate": True, "artifact_id": record["artifact_id"]}))
else: raise SystemExit(2)
