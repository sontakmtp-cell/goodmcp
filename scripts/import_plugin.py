"""Resumable G3 client, called after browser OAuth by connect-local.py."""
import hashlib
from pathlib import Path
import time
from uuid import uuid4


def upload_plugin(request, workspace_id, path, *, upload_id=None, enable=False, expected_revision=0):
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024): h.update(block)
    prefix = "/api/v1/workspaces/" + workspace_id

    def data(method, suffix, **kwargs):
        response = request(method, prefix + suffix, **kwargs)
        if response.status_code >= 300: raise RuntimeError("Import request failed: HTTP " + str(response.status_code))
        return response.json()["data"]

    if upload_id:
        upload = data("GET", "/uploads/" + str(upload_id))
        if upload["sha256"] != h.hexdigest() or upload["bytes"] != path.stat().st_size:
            raise RuntimeError("Resume ZIP differs from the original upload")
    else:
        upload = data("POST", "/uploads", json={"bytes":path.stat().st_size,"sha256":h.hexdigest(),"idempotency_key":uuid4().hex})
    uid = upload["id"]
    print("Upload handle (safe to save for --resume-upload): " + uid, flush=True)
    if upload["state"] == "uploading":
        with path.open("rb") as source:
            for part in range(upload["expected_parts"]):
                if part in upload["received_parts"]: continue
                source.seek(part * upload["part_size"])
                block = source.read(upload["part_size"])
                data("PUT", f"/uploads/{uid}/parts/{part}", content=block,
                     headers={"Content-Type":"application/octet-stream","X-Content-SHA256":hashlib.sha256(block).hexdigest()})
        upload = data("POST", f"/uploads/{uid}/complete")
    deadline = time.monotonic() + 1800
    while upload["state"] in ("queued", "scanning"):
        if time.monotonic() > deadline: raise RuntimeError("Import pending; use --resume-upload " + uid)
        time.sleep(1)
        upload = data("GET", "/uploads/" + uid)
    if upload["state"] != "ready": raise RuntimeError("Import did not pass: " + str(upload["error_code"] or upload["state"]))
    result = {"upload_id":uid, "version_id":upload["plugin_version_id"], "preview":upload["preview"], "enabled":False}
    if enable:
        installation = data("PUT", "/installation", json={"version_id":upload["plugin_version_id"],"enabled":True,"expected_revision":expected_revision})
        result.update(enabled=True, installation_id=installation["id"], revision=installation["revision"])
    return result
