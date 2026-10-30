"""Importer only: durable queue claim, immutable ZIP scan, atomic preview publication.

No module/CLI execution, dependency installation, document rendering or outbound I/O.
"""
from pathlib import Path
import os
from sqlalchemy import text
from .database import Principal
from .registry import Registry
from .plugin_scan import InvalidPackage, scan_zip
from .storage import IntegrityError


def process_one(database):
    with database.engine.begin() as conn:
        claim = conn.execute(text("SELECT * FROM hub_claim_import()")).mappings().one_or_none()
    if claim is None: return False
    principal = Principal(claim["user_id"], frozenset({"hub:read", "hub:write"}))
    try:
        with database.tenant(principal, claim["workspace_id"]) as t:
            registry = Registry(t, Path(os.environ.get("HUB_STORAGE_ROOT", "/data")))
            row = registry._row("plugin_uploads", claim["id"], lock=True)
            if row["lease_token"] != claim["lease_token"]: return True
            source = registry.assemble(row)
            with registry.store.open_verified(source.id) as handle: scan = scan_zip(handle)
            version = registry.publish_scan(scan, source)
            t.connection.execute(text("""UPDATE plugin_uploads SET state='ready',plugin_version_id=:v,source_artifact_id=:a,
                preview=CAST(:preview AS jsonb),lease_until=NULL WHERE workspace_id=:ws AND id=:id AND lease_token=:lease"""),
                {"v": version, "a": source.id, "preview": __import__("json").dumps(scan.preview()),
                 "ws": claim["workspace_id"], "id": claim["id"], "lease": claim["lease_token"]})
    except Exception as exc:
        # Parser/checksum failures are terminal. Unexpected worker faults retry after lease,
        # at most three attempts; after the third, expose a generic terminal failure.
        terminal = isinstance(exc, (InvalidPackage, IntegrityError))
        with database.tenant(principal, claim["workspace_id"]) as t:
            t.connection.execute(text("""UPDATE plugin_uploads SET state=CASE WHEN :terminal OR attempts>=3 THEN 'rejected' ELSE 'queued' END,
                error_code=:code,lease_until=NULL WHERE workspace_id=:ws AND id=:id AND lease_token=:lease"""),
                {"terminal": terminal, "code": str(exc) if isinstance(exc, InvalidPackage) else "import_failed",
                 "ws": claim["workspace_id"], "id": claim["id"], "lease": claim["lease_token"]})
        # No exception text, source paths or uploaded content in worker logs.
    return True
