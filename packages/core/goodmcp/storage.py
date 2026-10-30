"""Filesystem ArtifactStore. O_NOFOLLOW/openat anchors every generated component.

Public handles are UUIDs; filenames/keys from a client are never accepted.
Blob publication precedes the metadata transaction. Orphan reclamation and backup
pin accounting belong to later stages; deletion is a tombstone, not physical GC.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
from uuid import UUID, uuid4

from sqlalchemy import text
from .database import NotFound, TenantTransaction


class IntegrityError(Exception): pass
class Conflict(Exception): pass


@dataclass(frozen=True)
class ArtifactDescriptor:
    id: UUID
    sha256: str
    bytes: int
    media_type: str
    revision: int
    created_at: datetime


class ArtifactStore:
    def __init__(self, root: Path, tenant: TenantTransaction):
        self.root = Path(root)
        self.tenant = tenant
        self.prefix = ("workspaces", str(tenant.context.workspace_id))

    @contextmanager
    def _directory(self, components, *, create=False):
        # All callers supply server-generated UUID/hash segments, never user paths.
        descriptors = []
        try:
            descriptors.append(os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            for part in components:
                if not re.fullmatch(r"[a-zA-Z0-9_-]+", part):
                    raise IntegrityError("Invalid storage namespace")
                if create:
                    try: os.mkdir(part, mode=0o700, dir_fd=descriptors[-1])
                    except FileExistsError: pass
                descriptors.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                           dir_fd=descriptors[-1]))
            yield descriptors[-1]
        except OSError as exc:
            raise IntegrityError("Storage path is unavailable or unsafe") from exc
        finally:
            for fd in reversed(descriptors): os.close(fd)

    def put(self, chunks, media_type: str, *, max_bytes: int, expected_sha256=None, project_id=None):
        self.tenant.context.require_write()
        if max_bytes < 0 or not media_type or len(media_type) > 120:
            raise ValueError("Invalid artifact bounds")
        if expected_sha256 is not None and not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise ValueError("Invalid expected checksum")
        h, count, temp = hashlib.sha256(), 0, uuid4().hex
        with self._directory(self.prefix + ("tmp",), create=True) as temp_dir:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=temp_dir)
            try:
                with os.fdopen(fd, "wb") as output:
                    for chunk in chunks:
                        if not isinstance(chunk, bytes): raise TypeError("Byte stream required")
                        count += len(chunk)
                        if count > max_bytes: raise ValueError("Artifact exceeds byte limit")
                        h.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                    os.fchmod(output.fileno(), 0o400)
                checksum = h.hexdigest()
                if expected_sha256 is not None and checksum != expected_sha256:
                    raise IntegrityError("Artifact checksum mismatch")
                with self._directory(self.prefix + ("blobs",), create=True) as blob_dir:
                    try:
                        # link atomically publishes without overwriting another writer's blob.
                        os.link(temp, checksum, src_dir_fd=temp_dir, dst_dir_fd=blob_dir, follow_symlinks=False)
                    except FileExistsError:
                        self._read_blob(blob_dir, checksum, count)  # Reject symlink/corrupted dedup targets.
                    os.fsync(blob_dir)
            finally:
                os.unlink(temp, dir_fd=temp_dir)
                os.fsync(temp_dir)
        item_id = uuid4()
        key = "/".join(self.prefix + ("blobs", checksum))
        row = self.tenant.connection.execute(text("""INSERT INTO artifacts
            (id,workspace_id,project_id,created_by_user_id,sha256,bytes,media_type,storage_key)
            VALUES (:id,:ws,:project,:user,:hash,:bytes,:type,:key) RETURNING created_at"""),
            {"id": item_id, "ws": self.tenant.context.workspace_id, "project": project_id,
             "user": self.tenant.context.user_id, "hash": checksum, "bytes": count, "type": media_type, "key": key}).scalar_one()
        return ArtifactDescriptor(item_id, checksum, count, media_type, 1, row)

    def _row(self, artifact_id):
        # UUID parsing rejects path strings before any filesystem operation.
        artifact_id = UUID(str(artifact_id))
        row = self.tenant.connection.execute(text("SELECT * FROM artifacts WHERE id=:id AND workspace_id=:ws AND deleted_at IS NULL"),
            {"id": artifact_id, "ws": self.tenant.context.workspace_id}).mappings().one_or_none()
        if row is None: raise NotFound("Artifact not found")
        expected = "/".join(self.prefix + ("blobs", row["sha256"]))
        if row["storage_key"] != expected or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"]):
            raise IntegrityError("Storage metadata mismatch")
        return row

    def get(self, artifact_id):
        row = self._row(artifact_id)
        return ArtifactDescriptor(**{k: row[k] for k in ArtifactDescriptor.__dataclass_fields__})

    @staticmethod
    def _read_blob(directory, checksum, expected_size):
        fd = os.open(checksum, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        h, count = hashlib.sha256(), 0
        with os.fdopen(fd, "rb") as source:
            while block := source.read(1024 * 1024):
                h.update(block)
                count += len(block)
                if count > expected_size: raise IntegrityError("Stored blob size mismatch")
        if count != expected_size or h.hexdigest() != checksum:
            raise IntegrityError("Stored blob failed integrity check")

    def stream(self, artifact_id, byte_range=None):
        row = self._row(artifact_id)
        if byte_range is not None:
            start, stop = byte_range  # [start, stop), not HTTP inclusive end.
            if not (0 <= start < stop <= row["bytes"] and stop - start <= 8 * 1024 * 1024):
                raise ValueError("Invalid or oversized byte range")
        # Verify before yielding; stream without materializing whole large artifacts.
        with self._directory(self.prefix + ("blobs",)) as directory:
            try:
                fd = os.open(row["sha256"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError as exc:
                raise IntegrityError("Stored blob is unavailable or unsafe") from exc
            with os.fdopen(fd, "rb") as source:
                h, count = hashlib.sha256(), 0
                while block := source.read(1024 * 1024):
                    h.update(block)
                    count += len(block)
                if count != row["bytes"] or h.hexdigest() != row["sha256"]:
                    raise IntegrityError("Stored blob failed integrity check")
                start, stop = byte_range or (0, count)
                source.seek(start)
                while start < stop:
                    chunk = source.read(min(1024 * 1024, stop - start))
                    if not chunk: raise IntegrityError("Stored blob changed during read")
                    start += len(chunk)
                    yield chunk

    def delete(self, artifact_id, *, expected_revision):
        self.tenant.context.require_write()
        row = self._row(artifact_id)
        if row["revision"] != expected_revision or row["pin_count"] or row["project_id"] is not None:
            raise Conflict("Artifact revision conflict or artifact is pinned")
        linked = self.tenant.connection.execute(text("""SELECT EXISTS(SELECT 1 FROM resources WHERE artifact_id=:id)
            OR EXISTS(SELECT 1 FROM plugin_versions WHERE source_artifact_id=:id)
            OR EXISTS(SELECT 1 FROM jobs WHERE result_artifact_id=:id)"""), {"id": row["id"]}).scalar_one()
        if linked: raise Conflict("Artifact is referenced")
        count = self.tenant.connection.execute(text("""UPDATE artifacts SET deleted_at=now(),revision=revision+1
            WHERE id=:id AND revision=:revision AND pin_count=0 AND deleted_at IS NULL"""),
            {"id": row["id"], "revision": expected_revision}).rowcount
        if count != 1: raise Conflict("Artifact revision conflict")
        # Retain immutable blob: future backup/reference-aware GC is separate.
        return {"id": row["id"], "revision": expected_revision + 1, "tombstoned": True}
