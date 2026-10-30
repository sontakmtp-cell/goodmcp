import hashlib
import io
import json
import stat
import struct
import time
from uuid import uuid4
import zipfile

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from goodmcp.database import Forbidden, NotFound, Principal
from goodmcp.fixtures import WORKSPACE_A, WORKSPACE_B, USER_A, USER_B
from goodmcp.plugin_scan import scan_zip, InvalidPackage, tree_hash, CHUNK
from goodmcp.registry import Registry
from goodmcp.storage import Conflict, IntegrityError


def zipped(files=None, *, mode=zipfile.ZIP_STORED):
    entries = {"plugin.json": json.dumps({"name": "fourth-skill", "version": "1.0.0", "license": "MIT"}),
               "skills/hello/SKILL.md": "---\nname: hello\ndescription: A data-only fourth plugin.\n---\nHello Khầy.\n", **(files or {})}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=mode) as z:
        for p, data in entries.items(): z.writestr(p, data)
    return stream.getvalue()


def scan(raw): return scan_zip(io.BytesIO(raw))


def publish(r, raw):
    source = r.store.put([raw], "application/zip", max_bytes=len(raw))
    return r.publish_scan(scan(raw), source)


@pytest.mark.parametrize("path", ["../evil", "/abs", "C:/evil", "a\\b", "a/../b", "a//b", "a./b", "a/CON.txt", "a\x00z", "e\u0301.md"])
def test_zip_rejects_unsafe_names(path):
    raw = zipped({path: "bad"})
    # zipfile's writer truncates NUL: patch header names to exercise reader's orig_filename.
    if "\x00" in path:
        raw = zipped({"aXz": "bad"}).replace(b"aXz", b"a\0z")
    with pytest.raises(InvalidPackage): scan(raw)


def test_zip_duplicate_casefold_and_file_directory_collision():
    for files in ({"PLUGIN.JSON": "{}"}, {"a": "file", "a/b": "file"}, {"other/plugin.json": "{}"}):
        with pytest.raises(InvalidPackage): scan(zipped(files))


@pytest.mark.parametrize("mode", [stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600, stat.S_IFCHR | 0o600])
def test_zip_rejects_special_files(mode):
    b = io.BytesIO(zipped())
    with zipfile.ZipFile(b, "a") as z:
        item = zipfile.ZipInfo("special"); item.create_system = 3; item.external_attr = mode << 16
        z.writestr(item, "target")
    with pytest.raises(InvalidPackage): scan(b.getvalue())


def test_bomb_ratio_crc_truncation_and_size_limits():
    with pytest.raises(InvalidPackage, match="compression_ratio"): scan(zipped({"bomb": b"0" * 1048576}, mode=zipfile.ZIP_DEFLATED))
    raw = zipped({"a.txt": b"unique byte data"})
    with pytest.raises(InvalidPackage): scan(raw.replace(b"unique byte data", b"corruptbyte data"))
    with pytest.raises(InvalidPackage): scan(raw[:len(raw)//2])
    with pytest.raises(InvalidPackage): scan(b"not a ZIP")


def test_central_directory_expanded_size_count_encryption_limits():
    raw = bytearray(zipped())
    index = raw.index(b"PK\x01\x02")
    struct.pack_into("<I",raw,index+24,1024**3+1)
    with pytest.raises(InvalidPackage,match="expanded_limit"): scan(raw)
    raw = bytearray(zipped()); index=raw.index(b"PK\x01\x02")
    struct.pack_into("<H",raw,index+8,1)
    with pytest.raises(InvalidPackage,match="encrypted_zip"): scan(raw)
    with pytest.raises(InvalidPackage,match="file_count"): scan(zipped({f"f{i}":b"" for i in range(10001)}))


@pytest.mark.parametrize("files", [
    {".codex-plugin/plugin.json": '{"name":"conflict","version":"1.0.0"}'},
    {"plugin.json": '{"name":"fourth-skill","version":"1","version":"2"}'},
    {"plugin.json": '{"name":"fourth-skill","version":"1","skills":"./absent"}'},
    {"skills/bad/SKILL.md": "no front matter"},
    {"skills/duplicate/SKILL.md": "---\nname: hello\n---\nDuplicate"},
])
def test_manifest_conflicts_missing_entrypoints_invalid_roles(files):
    with pytest.raises(InvalidPackage): scan(zipped(files))


@pytest.mark.parametrize("files", [{".env": "PASSWORD=x"}, {"id_rsa": "secret"}, {"key.txt": "-----BEGIN PRIVATE KEY-----"}, {"test.py": "ghp_" + "a"*40}])
def test_known_secret_patterns_block_import(files):
    with pytest.raises(InvalidPackage, match="secret"): scan(zipped(files))


def test_data_only_scan_backup_and_warning_hash_portability(tmp_path):
    sentinel = tmp_path / "should-never-exist"
    raw = zipped({"scripts/danger.py": f"open({str(sentinel)!r},'w').write('executed'); raise Exception()",
        "evil.pkl": b"cos\nsystem\n(S'touch /tmp/pwned'\ntR.", "_backup_zh/skills/x/SKILL.md": "bad backup",
        "README.md": "[missing](absent.md)", "MANIFEST.json": '{"files":[{"filename":"missing.pdf","size_bytes":1}]}'})
    s = scan(raw)
    assert not sentinel.exists()
    assert len(s.skills) == 1 and not s.files["_backup_zh/skills/x/SKILL.md"]["active"]
    assert {"source_manifest_missing", "missing_document_reference", "supplied_index_untrusted_not_loaded"} <= {w["code"] for w in s.warnings}
    assert tree_hash(dict(reversed(list(s.files.items())))) == s.tree_sha256
    assert s.preview()["runtime"] == "source_only_no_execution"


def test_embedded_html_credential_is_quarantined_not_an_active_resource():
    s = scan(zipped({"captured.html": "<html>-----BEGIN PRIVATE KEY-----</html>"}))
    assert s.preview()["quarantined_files"] == 1
    assert not s.files["captured.html"]["active"]
    assert any(w["code"] == "embedded_credential_html_quarantined" for w in s.warnings)


@pytest.mark.parametrize("kind", ["codex", "codebuddy"])
def test_overlay_only_format_and_wrapped_root(kind):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(f"wrapper/.{kind}-plugin/plugin.json", '{"name":"only-overlay","version":"1","agents":"./agents/"}')
        z.writestr("wrapper/agents/expert.md", "---\nname: expert\n---\nA profile.")
    s = scan(b.getvalue())
    assert s.root == "wrapper/" and len(s.agents) == 1


def test_upload_resume_idempotency_boundaries(db, a, b, storage_root):
    raw = zipped(); checksum = hashlib.sha256(raw).hexdigest()
    with db.tenant(a, WORKSPACE_A) as t:
        r = Registry(t, storage_root)
        u = r.create_upload(len(raw), checksum, uuid4().hex)
        item = u["id"]
        assert r.upload(item)["received_parts"] == []
        with pytest.raises(Conflict): r.complete(item)
        with pytest.raises(IntegrityError): r.put_part(item, 0, raw, "0"*64)
        with pytest.raises(ValueError): r.put_part(item, 0, b"x", checksum)
        assert r.put_part(item, 0, raw, checksum)["received_parts"] == [0]
    with db.tenant(a, WORKSPACE_A) as t:
        r = Registry(t, storage_root)
        assert r.put_part(item, 0, raw, checksum)["received_parts"] == [0]
        with pytest.raises(ValueError): r.put_part(item, 1, raw, checksum)
        r.cancel(item)
        with pytest.raises(Conflict): r.put_part(item, 0, raw, checksum)
    with db.tenant(b, WORKSPACE_B) as t:
        with pytest.raises(NotFound): Registry(t, storage_root).upload(item)


def test_readonly_and_viewer_cannot_import(db, viewer, a, storage_root):
    for p in (viewer, Principal(USER_A, frozenset({"hub:read"}))):
        with db.tenant(p, WORKSPACE_A) as t:
            with pytest.raises(Forbidden): Registry(t, storage_root).create_upload(1, "0"*64, uuid4().hex)


def test_registry_version_install_disable_resources_export_and_isolation(db, a, b, storage_root):
    raw = zipped(); raw2 = zipped({"new.txt": "same manifest version, new bytes"})
    with db.tenant(a, WORKSPACE_A) as t:
        r = Registry(t, storage_root)
        v1 = publish(r, raw)
        assert publish(r, raw) == v1
        v2 = publish(r, raw2)
        assert v2 != v1
        project = r.c.execute(text("INSERT INTO projects(workspace_id,plugin_version_id,name) VALUES(:ws,:v,'Pinned G3') RETURNING id"), {"ws":WORKSPACE_A,"v":v1}).scalar_one()
        previous = r.c.execute(text("SELECT * FROM installations WHERE workspace_id=:w AND package_id=(SELECT package_id FROM plugin_versions WHERE id=:v)"), {"w": WORKSPACE_A, "v": v1}).mappings().one_or_none()
        i = r.set_installation(v1, True, previous["revision"] if previous else 0)
        iid = i["id"]
        assert r.role(iid, "skills", "hello")["body"].endswith("Hello Khầy.\n")
        assert b"".join(r.store.stream(r.export(v1).id)) == raw
        resource = r.resources(iid)["items"][0]
        assert r.read_resource(iid, resource["id"])["bytes"] == resource["metadata"]["bytes"]
        with pytest.raises(Conflict): r.set_installation(v2, True, i["revision"] - 1)
        disabled = r.set_installation(v1, False, i["revision"])
        with pytest.raises(NotFound): r.role(iid, "skills", "hello")
        r.set_installation(v2, True, disabled["revision"])
        assert r.open_plugin(iid)["version_id"] == v2
        assert r.c.execute(text("SELECT plugin_version_id FROM projects WHERE id=:id"), {"id":project}).scalar_one()==v1
        assert any(x["id"]==v1 and x["project_pins"]>=1 for x in r.versions(iid)["items"])
        # A failed new scan does not alter the selected installation/version.
        with pytest.raises(InvalidPackage): scan(zipped({"../bad": "bad"}))
        assert r.open_plugin(iid)["version_id"] == v2
    with db.tenant(b, WORKSPACE_B) as t:
        r = Registry(t, storage_root)
        for method, args in ((r.open_plugin, (iid,)), (r.export, (v1,)), (r.read_resource, (iid, resource["id"]))):
            with pytest.raises(NotFound): method(*args)


@pytest.mark.parametrize("table", ["plugin_uploads", "plugin_upload_parts"])
def test_g3_tables_force_rls_no_context(db, table):
    with db.engine.connect() as c:
        assert c.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=CAST(:t AS regclass)"), {"t": table}).one() == (True, True)
        assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_immutable_version_resources_and_pinned_zip(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        r = Registry(t, storage_root); version = publish(r, zipped({"immutable.txt": "forever"}))
        blob = r.export(version)
        with pytest.raises(Conflict): r.store.delete(blob.id, expected_revision=1)
    with pytest.raises(DBAPIError) as e:
        with db.tenant(a, WORKSPACE_A) as t:
            t.connection.execute(text("UPDATE plugin_versions SET manifest_version='forged' WHERE id=:v"), {"v": version})
    assert e.value.orig.sqlstate == "42501"


def test_upload_idempotency_conflict_and_quota(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        r = Registry(t, storage_root); key = uuid4().hex
        first = r.create_upload(1, "a"*64, key)
        assert r.create_upload(1, "a"*64, key)["id"] == first["id"]
        with pytest.raises(Conflict): r.create_upload(2, "a"*64, key)
        others = [r.create_upload(1, "a"*64, uuid4().hex) for _ in range(2)]
        with pytest.raises(Conflict): r.create_upload(1, "a"*64, uuid4().hex)
        for u in [first, *others]: r.cancel(u["id"])


def test_durable_claim_recovery_and_retry_exhaustion(db, a, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        r = Registry(t, storage_root)
        u = r.create_upload(1, "a"*64, uuid4().hex)
        t.connection.execute(text("UPDATE plugin_uploads SET state='queued' WHERE id=:id"), {"id":u["id"]})
        claimed = t.connection.execute(text("SELECT * FROM hub_claim_import()")).mappings().one()
        assert claimed["id"] == u["id"] and claimed["user_id"] == USER_A
        t.connection.execute(text("UPDATE plugin_uploads SET lease_until=now()-interval '1 second' WHERE id=:id"), {"id":u["id"]})
        claimed2 = t.connection.execute(text("SELECT * FROM hub_claim_import()")).mappings().one()
        assert claimed2["id"] == u["id"] and claimed2["lease_token"] != claimed["lease_token"]
        t.connection.execute(text("UPDATE plugin_uploads SET attempts=3,lease_until=now()-interval '1 second' WHERE id=:id"), {"id":u["id"]})
        assert t.connection.execute(text("SELECT * FROM hub_claim_import()")).first() is None
        assert r.upload(u["id"])["state"] == "rejected"


def test_upload_part_composite_fk_blocks_other_workspace(db, a, b, storage_root):
    with db.tenant(a, WORKSPACE_A) as t:
        r=Registry(t,storage_root); upload=r.create_upload(1,"a"*64,uuid4().hex); r.cancel(upload["id"])
    with pytest.raises(DBAPIError) as error:
        with db.tenant(b,WORKSPACE_B) as t:
            r=Registry(t,storage_root); blob=r.store.put([b"x"],"text/plain",max_bytes=1)
            t.connection.execute(text("INSERT INTO plugin_upload_parts(workspace_id,upload_id,part,artifact_id) VALUES(:w,:u,0,:a)"),
                {"w":WORKSPACE_B,"u":upload["id"],"a":blob.id})
    assert error.value.orig.sqlstate=="23503"
