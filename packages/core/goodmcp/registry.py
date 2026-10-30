"""Tenant registry/upload operations. Only reviewed importer calls publish_scan.

ZIP bytes and resource blobs use G1 ArtifactStore; SQL uses G1 tenant transactions.
"""
from dataclasses import asdict
import base64
import json
from pathlib import Path
import re
from uuid import UUID, uuid4
import zipfile

from sqlalchemy import text
from .database import Forbidden, NotFound
from .storage import ArtifactStore, Conflict, IntegrityError
from .plugin_scan import CHUNK, MAX_ZIP, Scan


def admin(t):
    t.context.require_write()
    if t.context.role not in ("owner", "admin"): raise Forbidden("Plugin administrator required")


class Registry:
    def __init__(self, tenant, root):
        self.t, self.c, self.ws = tenant, tenant.connection, tenant.context.workspace_id
        self.store = ArtifactStore(Path(root), tenant)

    def _params(self, **values): return {"ws": self.ws, **values}

    def _row(self, table, item_id, *, lock=False):
        assert table in ("plugin_uploads", "plugin_versions", "installations", "resources")
        row = self.c.execute(text(f"SELECT * FROM {table} WHERE workspace_id=:ws AND id=:id" + (" FOR UPDATE" if lock else "")),
                              self._params(id=UUID(str(item_id)))).mappings().one_or_none()
        if row is None: raise NotFound("Object not found")
        return row

    def audit(self, action, details):
        self.c.execute(text("""INSERT INTO audit_events(workspace_id,user_id,action,request_id,details)
            VALUES(:ws,:user,:action,:request,CAST(:details AS jsonb))"""), self._params(user=self.t.context.user_id,
            action=action, request=self.t.context.request_id, details=json.dumps(details)))

    def create_upload(self, size, checksum, key):
        admin(self.t)
        if not isinstance(size, int) or not 0 < size <= MAX_ZIP or not re.fullmatch(r"[a-f0-9]{64}", checksum) or not 1 <= len(key) <= 100:
            raise ValueError("Invalid upload bounds")
        # Serialize quota/idempotency decisions for this workspace, including concurrent requests.
        self.c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:ws,3))"), {"ws": str(self.ws)})
        old = self.c.execute(text("SELECT * FROM plugin_uploads WHERE workspace_id=:ws AND idempotency_key=:key"), self._params(key=key)).mappings().one_or_none()
        if old:
            if old["bytes"] != size or old["sha256"] != checksum: raise Conflict("Idempotency key already used")
            return self.upload(old["id"])
        active, reserved = self.c.execute(text("""SELECT count(*),coalesce(sum(bytes),0) FROM plugin_uploads
            WHERE workspace_id=:ws AND state IN ('uploading','queued','scanning') AND expires_at>now()"""), self._params()).one()
        stored = self.c.execute(text("SELECT coalesce(sum(bytes),0) FROM artifacts WHERE workspace_id=:ws AND deleted_at IS NULL"), self._params()).scalar_one()
        if active >= 3 or reserved + size > 4 * MAX_ZIP or stored + size * 4 > 20 * MAX_ZIP:
            raise Conflict("Workspace import quota reached")
        item = self.c.execute(text("""INSERT INTO plugin_uploads(workspace_id,user_id,idempotency_key,sha256,bytes)
            VALUES(:ws,:user,:key,:hash,:size) RETURNING id"""), self._params(user=self.t.context.user_id, key=key, hash=checksum, size=size)).scalar_one()
        self.audit("plugin_upload_created", {"upload_id": str(item), "bytes": size})
        return self.upload(item)

    def upload(self, item_id):
        row = self._row("plugin_uploads", item_id)
        parts = self.c.execute(text("SELECT part FROM plugin_upload_parts WHERE workspace_id=:ws AND upload_id=:id ORDER BY part"), self._params(id=row["id"])).scalars().all()
        return {k: row[k] for k in ("id", "bytes", "sha256", "state", "plugin_version_id", "preview", "error_code", "expires_at")} | {
            "part_size": CHUNK, "received_parts": parts, "expected_parts": (row["bytes"] + CHUNK - 1) // CHUNK}

    def put_part(self, item_id, part, content, checksum):
        admin(self.t)
        row = self._row("plugin_uploads", item_id, lock=True)
        if row["state"] != "uploading" or self._expired(row): raise Conflict("Upload is not writable")
        if not isinstance(part, int) or not 0 <= part < (row["bytes"] + CHUNK - 1) // CHUNK: raise ValueError("Invalid part number")
        expected = min(CHUNK, row["bytes"] - part * CHUNK)
        if len(content) != expected: raise ValueError("Invalid part length")
        old = self.c.execute(text("""SELECT a.sha256 FROM plugin_upload_parts p JOIN artifacts a ON a.id=p.artifact_id AND a.workspace_id=p.workspace_id
            WHERE p.workspace_id=:ws AND upload_id=:id AND part=:part"""), self._params(id=row["id"], part=part)).scalar_one_or_none()
        import hashlib
        actual = hashlib.sha256(content).hexdigest()
        if actual != checksum: raise IntegrityError("Chunk checksum mismatch")
        if old is not None:
            if old != actual: raise Conflict("Part already uploaded with different content")
            return self.upload(item_id)
        blob = self.store.put([content], "application/octet-stream", max_bytes=CHUNK, expected_sha256=checksum)
        self.c.execute(text("INSERT INTO plugin_upload_parts(workspace_id,upload_id,part,artifact_id) VALUES(:ws,:id,:part,:blob)"),
                       self._params(id=row["id"], part=part, blob=blob.id))
        return self.upload(item_id)

    def _expired(self, row):
        return self.c.execute(text("SELECT :expires < now()"), {"expires": row["expires_at"]}).scalar_one()

    def complete(self, item_id):
        admin(self.t)
        row = self._row("plugin_uploads", item_id, lock=True)
        if row["state"] in ("queued", "scanning", "ready"): return self.upload(item_id)
        if row["state"] != "uploading" or self._expired(row): raise Conflict("Upload is not writable")
        status = self.upload(item_id)
        if status["received_parts"] != list(range(status["expected_parts"])): raise Conflict("Upload has missing parts")
        self.c.execute(text("UPDATE plugin_uploads SET state='queued' WHERE id=:id AND workspace_id=:ws"), self._params(id=row["id"]))
        self.audit("plugin_import_queued", {"upload_id": str(row["id"])})
        return self.upload(item_id)

    def cancel(self, item_id):
        admin(self.t)
        row = self._row("plugin_uploads", item_id, lock=True)
        if row["state"] == "scanning": raise Conflict("Import is already being checked")
        if row["state"] in ("uploading", "queued"):
            self.c.execute(text("UPDATE plugin_uploads SET state='cancelled' WHERE id=:id AND workspace_id=:ws"), self._params(id=row["id"]))
        return self.upload(item_id)

    def assemble(self, row):
        parts = self.c.execute(text("SELECT artifact_id FROM plugin_upload_parts WHERE workspace_id=:ws AND upload_id=:id ORDER BY part"), self._params(id=row["id"])).scalars().all()
        def blocks():
            for part in parts: yield from self.store.stream(part)
        return self.store.put(blocks(), "application/zip", max_bytes=row["bytes"], expected_sha256=row["sha256"])

    def publish_scan(self, scan: Scan, source_artifact):
        """Atomic registry publication after whole-ZIP validation. Does not enable installation."""
        admin(self.t)
        self.c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,4))"), {"key": str(self.ws) + scan.manifest["name"]})
        package = self.c.execute(text("""INSERT INTO plugin_packages(workspace_id,name,license)
            VALUES(:ws,:name,:license) ON CONFLICT(workspace_id,name) DO UPDATE SET name=EXCLUDED.name RETURNING id"""),
            self._params(name=scan.manifest["name"], license=scan.manifest.get("license"))).scalar_one()
        existing = self.c.execute(text("""SELECT id FROM plugin_versions WHERE workspace_id=:ws AND package_id=:p
            AND manifest_version=:v AND source_sha256=:hash"""), self._params(p=package, v=scan.manifest["version"], hash=source_artifact.sha256)).scalar_one_or_none()
        if existing: return existing
        version = uuid4()
        metadata = {"manifest": scan.manifest, "preview": scan.preview(), "warnings": scan.warnings,
                    "tree_sha256": scan.tree_sha256, "tree_hash_format": "goodmcp-tree-v1"}
        self.c.execute(text("""INSERT INTO plugin_versions(id,workspace_id,package_id,manifest_version,source_sha256,source_artifact_id,metadata)
            VALUES(:id,:ws,:p,:v,:hash,:source,CAST(:data AS jsonb))"""), self._params(id=version, p=package,
            v=scan.manifest["version"], hash=source_artifact.sha256, source=source_artifact.id, data=json.dumps(metadata)))
        with self.store.open_verified(source_artifact.id) as handle, zipfile.ZipFile(handle) as z:
            for path, f in scan.files.items():
                with z.open(f["zip_path"]) as stream:
                    blob = self.store.put(iter(lambda: stream.read(1024 * 1024), b""), "application/octet-stream",
                                          max_bytes=f["bytes"], expected_sha256=f["sha256"])
                self.c.execute(text("""INSERT INTO resources(workspace_id,plugin_version_id,artifact_id,logical_path,metadata)
                    VALUES(:ws,:v,:a,:path,CAST(:data AS jsonb))"""), self._params(v=version, a=blob.id, path=path,
                    data=json.dumps({k: f[k] for k in ("sha256", "bytes", "active", "quarantined")})))
        for table, roles in (("skills", scan.skills), ("agents", scan.agents)):
            for role in roles:
                self.c.execute(text(f"INSERT INTO {table}(workspace_id,plugin_version_id,name,body) VALUES(:ws,:v,:name,:body)"),
                    self._params(v=version, name=role["name"], body=role["body"]))
        self.audit("plugin_version_imported", {"version_id": str(version), "zip_sha256": source_artifact.sha256, "tree_sha256": scan.tree_sha256})
        return version

    def set_installation(self, version_id, enabled, expected_revision):
        admin(self.t)
        v = self._row("plugin_versions", version_id)
        self.c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,5))"), {"key": str(self.ws) + str(v["package_id"])})
        old = self.c.execute(text("SELECT * FROM installations WHERE workspace_id=:ws AND package_id=:p FOR UPDATE"), self._params(p=v["package_id"])).mappings().one_or_none()
        if (old["revision"] if old else 0) != expected_revision: raise Conflict("Installation revision conflict")
        if old:
            self.c.execute(text("UPDATE installations SET plugin_version_id=:v,enabled=:e,revision=revision+1 WHERE workspace_id=:ws AND id=:id"), self._params(v=v["id"], e=enabled, id=old["id"]))
            item_id = old["id"]
        else:
            item_id = self.c.execute(text("""INSERT INTO installations(workspace_id,package_id,plugin_version_id,enabled)
                VALUES(:ws,:p,:v,:e) RETURNING id"""), self._params(p=v["package_id"], v=v["id"], e=enabled)).scalar_one()
        self.audit("plugin_installation_changed", {"version_id": str(v["id"]), "enabled": enabled, "revision": expected_revision + 1})
        return dict(self._row("installations", item_id))

    def list_plugins(self, cursor=None, limit=50):
        if not 1 <= limit <= 100: raise ValueError("Invalid page size")
        rows = self.c.execute(text("""SELECT i.id AS installation_id,i.plugin_version_id,i.enabled,i.revision,p.name,v.manifest_version,
            v.metadata->'preview' AS preview FROM installations i JOIN plugin_versions v ON v.id=i.plugin_version_id AND v.workspace_id=i.workspace_id
            JOIN plugin_packages p ON p.id=v.package_id AND p.workspace_id=v.workspace_id
            WHERE i.workspace_id=:ws AND (CAST(:cursor AS uuid) IS NULL OR i.id>CAST(:cursor AS uuid)) ORDER BY i.id LIMIT :limit"""),
            self._params(cursor=str(UUID(str(cursor))) if cursor else None, limit=limit + 1)).mappings().all()
        return {"items": [dict(r) for r in rows[:limit]], "next_cursor": str(rows[limit - 1]["installation_id"]) if len(rows) > limit else None}

    def active_version(self, installation_id):
        i = self._row("installations", installation_id)
        if not i["enabled"]: raise NotFound("Installation unavailable")
        return self._row("plugin_versions", i["plugin_version_id"])

    def versions(self, installation_id, cursor=None, limit=50):
        if not 1 <= limit <= 100: raise ValueError("Invalid page size")
        installation = self._row("installations", installation_id)
        rows = self.c.execute(text("""SELECT v.id,v.manifest_version,v.source_sha256,v.metadata->>'tree_sha256' AS tree_sha256,
            v.created_at,(SELECT count(*) FROM projects p WHERE p.workspace_id=v.workspace_id AND p.plugin_version_id=v.id) AS project_pins
            FROM plugin_versions v WHERE v.workspace_id=:ws AND v.package_id=:p
            AND (CAST(:cursor AS uuid) IS NULL OR v.id>CAST(:cursor AS uuid)) ORDER BY v.id LIMIT :limit"""),
            self._params(p=installation["package_id"], cursor=str(UUID(str(cursor))) if cursor else None,limit=limit+1)).mappings().all()
        return {"items":[dict(r) for r in rows[:limit]],"next_cursor":str(rows[limit-1]["id"]) if len(rows)>limit else None}

    def open_plugin(self, installation_id):
        v = self.active_version(installation_id)
        return {"version_id": v["id"], "manifest_version": v["manifest_version"], "zip_sha256": v["source_sha256"], "preview": v["metadata"]["preview"]}

    def role(self, installation_id, kind, name):
        if kind not in ("skills", "agents") or not re.fullmatch(r"[a-z0-9_-]{1,100}", name): raise ValueError("Invalid role")
        v = self.active_version(installation_id)
        row = self.c.execute(text(f"SELECT id,name,body FROM {kind} WHERE workspace_id=:ws AND plugin_version_id=:v AND name=:name"),
                             self._params(v=v["id"], name=name)).mappings().one_or_none()
        if row is None: raise NotFound("Role not found")
        if len(row["body"].encode()) > 128 * 1024: raise ValueError("Use paged resource to read this role")
        return dict(row) | {"version_id": v["id"], "source_trust": "plugin_content_not_system_instructions"}

    def resources(self, installation_id, cursor=None, limit=50):
        if not 1 <= limit <= 100: raise ValueError("Invalid page size")
        v = self.active_version(installation_id)
        rows = self.c.execute(text("""SELECT id,logical_path,metadata FROM resources WHERE workspace_id=:ws AND plugin_version_id=:v
            AND (metadata->>'active')::boolean AND (CAST(:cursor AS uuid) IS NULL OR id>CAST(:cursor AS uuid)) ORDER BY id LIMIT :limit"""),
            self._params(v=v["id"], cursor=str(UUID(str(cursor))) if cursor else None, limit=limit + 1)).mappings().all()
        return {"items": [dict(r) for r in rows[:limit]], "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None}

    def read_resource(self, installation_id, resource_id, offset=0, length=16384):
        v = self.active_version(installation_id)
        r = self._row("resources", resource_id)
        if r["plugin_version_id"] != v["id"] or not r["metadata"]["active"]: raise NotFound("Resource unavailable")
        if not 0 <= offset <= r["metadata"]["bytes"] or not 1 <= length <= 65536: raise ValueError("Invalid resource range")
        stop = min(offset + length, r["metadata"]["bytes"])
        raw = b"".join(self.store.stream(r["artifact_id"], (offset, stop))) if stop > offset else b""
        return {"resource_id": r["id"], "logical_path": r["logical_path"], "sha256": r["metadata"]["sha256"],
            "bytes": r["metadata"]["bytes"], "offset": offset, "next_offset": stop if stop < r["metadata"]["bytes"] else None,
            "encoding": "base64", "content": base64.b64encode(raw).decode(), "source_trust": "plugin_content_not_system_instructions"}

    def export(self, version_id):
        v = self._row("plugin_versions", version_id)
        return self.store.get(v["source_artifact_id"])
