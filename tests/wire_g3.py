"""Real loopback HTTP + official MCP SDK; input ZIPs are read-only external fixtures.

No credentials printed. Private restart state lives in the harness-owned wire volume.
"""
import asyncio
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import zipfile

import httpx
import httpx2
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from test_registry import zipped

BASE = os.environ["HUB_PUBLIC_BASE_URL"].rstrip("/")
STATE = Path("/wirestate/g3.json")
checks = []


def check(name, condition, **extra):
    checks.append({"name": name, "passed": bool(condition), **extra})
    if not condition: raise AssertionError(name)


def csrf(response):
    assert response.status_code == 200
    return html.unescape(re.search(r'name="csrf"[^>]*value="([^"\s]+)"', response.text)[1])


def login(scope="hub:read hub:write"):
    browser = httpx.Client(base_url=BASE, timeout=30)
    redirect = "http://127.0.0.1:8766/callback"
    reg = browser.post("/auth/register", json={"client_name": "G3 local acceptance", "redirect_uris": [redirect], "scope": scope})
    assert reg.status_code == 201
    client = reg.json()["client_id"]
    page = browser.get("/auth/login")
    password = Path("/run/secrets/owner_password").read_text().strip()
    assert browser.post("/auth/login", data={"csrf": csrf(page), "email": "owner@local.invalid", "password": password}).status_code == 303
    verifier = secrets.token_urlsafe(48); state = secrets.token_urlsafe(24)
    page = browser.get("/auth/authorize", params={"response_type": "code", "client_id": client, "redirect_uri": redirect,
        "resource": BASE + "/mcp", "scope": scope, "state": state, "code_challenge_method": "S256",
        "code_challenge": create_s256_code_challenge(verifier)})
    options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', page.text)
    ws = next(value for value, label in options if "G2 revoked fixture" not in label)
    result = browser.post("/auth/authorize", data={"csrf": csrf(page), "consent": "allow", "workspace_id": ws})
    fields = parse_qs(urlsplit(result.headers["location"]).query)
    assert fields["state"] == [state] and fields["iss"] == [BASE + "/auth"]
    result = browser.post("/auth/token", data={"grant_type": "authorization_code", "client_id": client, "redirect_uri": redirect,
        "resource": BASE + "/mcp", "code": fields["code"][0], "code_verifier": verifier})
    assert result.status_code == 200
    return {**result.json(), "client_id": client, "workspace_id": ws}


class API:
    def __init__(self, credentials):
        self.credentials = credentials
        self.client = httpx.Client(base_url=BASE, timeout=180)
        self.prefix = "/api/v1/workspaces/" + credentials["workspace_id"]

    def request(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        response = self.client.request(method, self.prefix + path, headers={"Authorization": "Bearer " + self.credentials["access_token"], **headers}, **kwargs)
        if response.status_code == 401:
            result = self.client.post("/auth/token", data={"grant_type": "refresh_token", "client_id": self.credentials["client_id"],
                "refresh_token": self.credentials["refresh_token"], "resource": BASE + "/mcp"})
            assert result.status_code == 200
            self.credentials.update(result.json())
            response = self.client.request(method, self.prefix + path, headers={"Authorization": "Bearer " + self.credentials["access_token"], **headers}, **kwargs)
        return response

    def data(self, method, path, **kwargs):
        response = self.request(method, path, **kwargs)
        assert response.status_code < 300, (method, path, response.status_code, response.text[:200])
        return response.json()["data"]

    def upload(self, raw=None, path=None, *, resume_probe=False):
        h = hashlib.sha256(); size = 0
        if path:
            with path.open("rb") as f:
                while b := f.read(1024*1024): h.update(b); size += len(b)
        else: h.update(raw); size = len(raw)
        payload = {"bytes": size, "sha256": h.hexdigest(), "idempotency_key": uuid4().hex}
        u = self.data("POST", "/uploads", json=payload)
        if resume_probe:
            check("idempotent create", self.data("POST", "/uploads", json=payload)["id"] == u["id"])
            check("complete rejects missing parts", self.request("POST", f'/uploads/{u["id"]}/complete').status_code == 409)
        import io
        f = path.open("rb") if path else io.BytesIO(raw)
        with f:
            for part in reversed(range(u["expected_parts"])):
                f.seek(part*u["part_size"]); block = f.read(u["part_size"])
                r = self.data("PUT", f'/uploads/{u["id"]}/parts/{part}', content=block,
                    headers={"X-Content-SHA256": hashlib.sha256(block).hexdigest(), "Content-Type": "application/octet-stream"})
                if resume_probe and part == u["expected_parts"]-1:
                    resumed = self.data("GET", f'/uploads/{u["id"]}')
                    check("out-of-order chunk visible on resume", resumed["received_parts"] == [part])
                    repeated = self.data("PUT", f'/uploads/{u["id"]}/parts/{part}', content=block,
                        headers={"X-Content-SHA256": hashlib.sha256(block).hexdigest()})
                    check("chunk retry no duplicate", repeated["received_parts"] == [part])
        assert self.request("POST", f'/uploads/{u["id"]}/complete').status_code == 202
        start=time.monotonic()
        while time.monotonic()-start < 240:
            status = self.data("GET", f'/uploads/{u["id"]}')
            if status["state"] in ("ready", "rejected"): return status
            time.sleep(0.25)
        raise AssertionError("import worker timed out")

    def export_check(self, version, expected, *, inspect_files=False):
        response = self.request("GET", f"/versions/{version}/export") if expected["zip_bytes"] < 1024*1024 else None
        target = Path("/wirestate/export.zip")
        h = hashlib.sha256(); count=0
        if response is not None:
            assert response.status_code == 200
            target.write_bytes(response.content); h.update(response.content); count=len(response.content)
        else:
            with self.client.stream("GET", self.prefix + f"/versions/{version}/export", headers={"Authorization": "Bearer " + self.credentials["access_token"]}) as response:
                assert response.status_code == 200
                assert response.headers["content-disposition"].startswith("attachment") and response.headers["x-content-type-options"] == "nosniff"
                with target.open("wb") as f:
                    for block in response.iter_bytes(1024*1024): f.write(block); h.update(block); count+=len(block)
        check("ZIP export byte identity: " + expected["directory"], h.hexdigest() == expected["zip_sha256"] and count == expected["zip_bytes"])
        if inspect_files:
            with zipfile.ZipFile(target) as z:
                check("export file count: " + expected["directory"], len(z.namelist()) == len(expected["files"]))
                for path, meta in expected["files"].items():
                    checksum = hashlib.sha256()
                    with z.open(path) as f:
                        while b := f.read(1024*1024): checksum.update(b)
                    assert checksum.hexdigest() == meta["sha256"], path
            check("all exported file hashes: " + expected["directory"], True, files=len(expected["files"]))
        target.unlink()


def full():
    api = API(login()); samples=json.loads(Path("/samples/samples.json").read_text())
    check("G0 source hashes rechecked", samples["g0_files_rechecked"])
    readonly = API(login("hub:read"))
    check("read-only token cannot upload", readonly.request("POST", "/uploads", json={"bytes":1,"sha256":"0"*64,"idempotency_key":uuid4().hex}).status_code == 403)
    check("foreign workspace route blocked", api.client.get(BASE + "/api/v1/workspaces/20000000-0000-4000-8000-000000000002/plugins", headers={"Authorization":"Bearer " + api.credentials["access_token"]}).status_code == 404)
    check("unknown input field rejected", api.request("POST", "/uploads", json={"bytes":1,"sha256":"0"*64,"idempotency_key":uuid4().hex,"module":"evil"}).status_code == 422)
    oversized = api.request("PUT", "/uploads/"+str(uuid4())+"/parts/0", content=b"x"*(8*1024*1024+1))
    check("body over 8 MiB rejected before storage", oversized.status_code==413 and oversized.json()["error"]["code"]=="invalid_input")
    records=[]
    for sample in samples["packages"]:
        start=time.monotonic()
        result=api.upload(path=Path("/samples") / sample["zip"], resume_probe=True)
        check("validated sample: " + sample["directory"], result["state"] == "ready", error_code=result["error_code"])
        preview=result["preview"]
        check("portable tree hash: " + sample["directory"], preview["tree_sha256"] == sample["tree_sha256"])
        i=api.data("PUT", "/installation", json={"version_id":result["plugin_version_id"],"enabled":True,"expected_revision":0})
        api.export_check(result["plugin_version_id"], sample, inspect_files=True)
        count=0; cursor=None
        while True:
            page=api.data("GET", f'/installations/{i["id"]}/resources', params={"limit":100, **({"cursor":cursor} if cursor else {})})
            for resource in page["items"]:
                assert resource["metadata"]["sha256"] == sample["files"][resource["logical_path"]]["sha256"]
                assert "_backup_zh" not in resource["logical_path"].split("/")
            count+=len(page["items"]); cursor=page["next_cursor"]
            if not cursor: break
        check("paged active resource hashes: " + sample["directory"], count == sum("_backup_zh" not in p.split("/") for p in sample["files"]) - preview["quarantined_files"])
        records.append({"installation":i, "version_id":result["plugin_version_id"], "preview":preview,
                        "directory":sample["directory"], "elapsed_s":round(time.monotonic()-start,3)})
    check("three plugins and sixteen roles", len(records)==3 and sum(r["preview"]["roles"] for r in records)==16)
    fourth=api.upload(raw=zipped())
    check("fourth data-only plugin accepted", fourth["state"]=="ready" and fourth["preview"]["roles"]==1)
    i=api.data("PUT", "/installation", json={"version_id":fourth["plugin_version_id"],"enabled":True,"expected_revision":0})
    invalid=api.upload(raw=zipped({"../escape.txt":"bad"}))
    check("worker rejects traversal", invalid["state"]=="rejected" and invalid["error_code"]=="unsafe_path")
    check("invalid version leaves active installation", api.data("GET", f'/installations/{i["id"]}') ["version_id"]==fourth["plugin_version_id"])
    revision=api.upload(raw=zipped({"revision.txt":"same manifest version, new content"}))
    check("same manifest version gets content revision", revision["state"]=="ready" and revision["plugin_version_id"]!=fourth["plugin_version_id"])
    check("stale installation revision rejected", api.request("PUT", "/installation", json={"version_id":revision["plugin_version_id"],"enabled":True,"expected_revision":0}).status_code==409)
    i=api.data("PUT", "/installation", json={"version_id":revision["plugin_version_id"],"enabled":True,"expected_revision":i["revision"]})
    records.append({"installation":i,"version_id":revision["plugin_version_id"],"preview":revision["preview"],"directory":"fourth-skill"})
    asyncio.run(sdk_tests(api, records))
    partial = zipped({"resume.bin": b"r" * (8*1024*1024+17)})
    Path("/wirestate/partial.zip").write_bytes(partial)
    upload = api.data("POST", "/uploads", json={"bytes":len(partial),"sha256":hashlib.sha256(partial).hexdigest(),"idempotency_key":uuid4().hex})
    part = partial[:upload["part_size"]]
    api.data("PUT", f'/uploads/{upload["id"]}/parts/0', content=part, headers={"X-Content-SHA256":hashlib.sha256(part).hexdigest()})
    state={"credentials":api.credentials,"records":records,"partial_upload":upload["id"]}
    STATE.write_text(json.dumps(state))
    return {"plugins": [{k:r[k] for k in ("directory","version_id","preview")} | {"elapsed_s":r.get("elapsed_s")} for r in records],
            "source_files_verified":sum(len(s["files"]) for s in samples["packages"]),"source_snapshot":samples["source"]}


async def sdk_tests(api, records):
    async with httpx2.AsyncClient(headers={"Authorization":"Bearer " + api.credentials["access_token"]}, timeout=60) as http:
        async with Client(streamable_http_client(BASE + "/mcp", http_client=http), mode="2026-07-28") as client:
            check("G3 SDK protocol pin", client.protocol_version=="2026-07-28")
            tools=await client.list_tools()
            check("catalog tools available, no execution", {t.name for t in tools.tools}=={"hub_get_workspace","hub_list_plugins","hub_open_plugin","hub_get_skill","hub_get_agent","hub_list_resources","hub_read_resource"})
            seen=[]; cursor=None
            while True:
                r=await client.call_tool("hub_list_plugins", {"limit":1, **({"cursor":cursor} if cursor else {})})
                assert not r.is_error
                seen+=r.structured_content["items"]; cursor=r.structured_content["next_cursor"]
                if not cursor: break
            check("MCP pagination has four plugins", len(seen)==4)
            for record in records:
                iid=record["installation"]["id"]
                r=await client.call_tool("hub_open_plugin", {"installation_id":iid})
                check("MCP opens version: " + record["directory"], not r.is_error and r.structured_content["version_id"]==record["version_id"])
                for kind in ("skills", "agents"):
                    for role in record["preview"][kind]:
                        r=await client.call_tool("hub_get_skill" if kind=="skills" else "hub_get_agent", {"installation_id":iid,"name":role["name"]})
                        expected=record["directory"]
                        check("MCP role: " + role["name"], not r.is_error and r.structured_content["name"]==role["name"])
                page=await client.call_tool("hub_list_resources", {"installation_id":iid,"limit":100})
                resource=page.structured_content["items"][0]
                r=await client.call_tool("hub_read_resource", {"installation_id":iid,"resource_id":resource["id"],"length":64})
                check("MCP bounded resource: " + record["directory"], not r.is_error and len(base64.b64decode(r.structured_content["content"]))<=64)
                r=await client.call_tool("hub_read_resource", {"installation_id":iid,"resource_id":str(uuid4())})
                check("unknown resource fails: " + record["directory"], r.is_error)
            iid=records[-1]["installation"]["id"]
            disabled=api.data("PUT", "/installation", json={"version_id":records[-1]["version_id"],"enabled":False,"expected_revision":records[-1]["installation"]["revision"]})
            result=await client.call_tool("hub_get_skill", {"installation_id":iid,"name":"hello"})
            check("disabled installation blocks MCP reads", result.is_error)
            enabled=api.data("PUT", "/installation", json={"version_id":records[-1]["version_id"],"enabled":True,"expected_revision":disabled["revision"]})
            records[-1]["installation"]=enabled


def resume():
    state=json.loads(STATE.read_text()); api=API(state["credentials"])
    records=state["records"]
    upload=api.data("GET", "/uploads/" + state["partial_upload"])
    check("partial upload survives container recreation", upload["received_parts"]==[0] and upload["state"]=="uploading")
    raw=Path("/wirestate/partial.zip").read_bytes()
    part=raw[upload["part_size"]:]
    api.data("PUT", f'/uploads/{upload["id"]}/parts/1', content=part, headers={"X-Content-SHA256":hashlib.sha256(part).hexdigest()})
    api.data("POST", f'/uploads/{upload["id"]}/complete')
    for _ in range(120):
        result=api.data("GET", "/uploads/" + upload["id"])
        if result["state"] in ("ready","rejected"): break
        time.sleep(0.25)
    check("resume remaining chunk and finish after recreation", result["state"]=="ready")
    Path("/wirestate/partial.zip").unlink()
    for r in records:
        result=api.data("GET", f'/installations/{r["installation"]["id"]}')
        check("version persists: " + r["directory"], result["version_id"]==r["version_id"] and result["preview"]["tree_sha256"]==r["preview"]["tree_sha256"])
    samples=json.loads(Path("/samples/samples.json").read_text())
    for sample in samples["packages"]:
        record=next(r for r in records if r["directory"]==sample["directory"])
        api.export_check(record["version_id"], sample)
    check("all versions survive full container recreation", True)
    return {"versions":len(records),"zip_exports_rechecked":3}


if __name__=="__main__":
    result=full() if sys.argv[1]=="full" else resume()
    print(json.dumps({"passed":True,"checks":checks,**result},ensure_ascii=False))
