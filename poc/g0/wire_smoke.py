"""Real loopback TCP login -> Authlib S256 -> token -> SDK v2 tool, no model API."""
import asyncio
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import httpx2
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

BASE = "http://127.0.0.1:8765"
RESOURCE = BASE + "/mcp"
CALLBACK = BASE + "/callback"
OUT = Path("/work")


def serve(password, fixtures):
    # Explicit loopback-only exception, never set in production.
    os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["G0_OWNER_PASSWORD"] = password
    import auth_poc
    for token, overrides in fixtures.items():
        auth_poc.tokens[token] = {"client_id": "g0-local-client", "scope": "hub:read",
            "expires_at": int(time.time()) + 300, "resource": RESOURCE,
            **auth_poc.OWNER, **overrides}
    import uvicorn
    uvicorn.run(auth_poc.app, host="127.0.0.1", port=8765, access_log=False, log_level="warning")


async def smoke(password, fixtures):
    checks, wire = [], []

    def check(name, condition, **evidence):
        checks.append({"name": name, "passed": bool(condition), **evidence})
        if not condition:
            (OUT / "wire-auth-failure.json").write_text(json.dumps({"checks": checks, "wire": wire}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(checks[-1]), flush=True)
        assert condition, name

    async with httpx.AsyncClient(base_url=BASE, timeout=15) as browser:
        for _ in range(100):
            try:
                if (await browser.get("/health")).status_code == 200: break
            except httpx.ConnectError: pass
            await asyncio.sleep(0.1)
        else: raise RuntimeError("PoC server did not become ready")
        md = await browser.get("/.well-known/oauth-authorization-server")
        check("AS discovery", md.status_code == 200 and md.json()["code_challenge_methods_supported"] == ["S256"])
        denied = await browser.post("/mcp", json={})
        check("missing token", denied.status_code == 401, status=denied.status_code,
              challenge=denied.headers.get("www-authenticate"))
        resource_md = await browser.get("/.well-known/oauth-protected-resource/mcp")
        check("resource discovery", resource_md.status_code == 200 and resource_md.json()["resource"] == RESOURCE,
              metadata=resource_md.json())
        req = {"client_id": "g0-local-client", "response_type": "code", "redirect_uri": CALLBACK,
               "scope": "hub:read", "resource": RESOURCE, "state": secrets.token_urlsafe(24),
               "code_challenge": create_s256_code_challenge("v" * 64), "code_challenge_method": "S256"}
        r = await browser.get("/authorize", params=req)
        check("authorize needs login", r.status_code == 401)
        r = await browser.post("/login", data={"password": password, "csrf": "wrong"})
        check("login CSRF", r.status_code == 403)

        async def login(pwd):
            r = await browser.get("/login")
            csrf = re.search(r'value="([^"\s]+)"', r.text)[1]
            return await browser.post("/login", data={"password": pwd, "csrf": csrf})

        check("bad password", (await login("bad-password")).status_code == 401)
        r = await login(password)
        check("owner login", r.status_code == 200 and "g0-session" in browser.cookies)
        r = await browser.get("/authorize", params={**req, "redirect_uri": "http://127.0.0.1:8765/evil"})
        check("unregistered redirect", r.status_code == 400 and "location" not in r.headers, status=r.status_code)
        no_pkce = {k: v for k, v in req.items() if not k.startswith("code_challenge")}
        check("PKCE required", (await browser.get("/authorize", params=no_pkce)).status_code == 400)
        r = await browser.get("/authorize", params={**req, "resource": BASE + "/wrong"})
        check("authorize resource", r.status_code == 400)
        r = await browser.get("/authorize", params=req)
        fields = parse_qs(urlsplit(r.headers.get("location", "")).query)
        check("authorize S256 and state", r.status_code == 302 and fields.get("state") == [req["state"]] and "code" in fields)
        code = fields["code"][0]
        form = {"grant_type": "authorization_code", "client_id": "g0-local-client", "code": code,
                "redirect_uri": CALLBACK, "code_verifier": "v" * 64, "resource": RESOURCE}
        r = await browser.post("/token", data={**form, "code_verifier": "w" * 64})
        check("wrong verifier", r.status_code == 400 and r.json()["error"] == "invalid_grant")
        r = await browser.post("/token", data={**form, "resource": BASE + "/wrong"})
        check("token resource", r.status_code == 400)
        r = await browser.post("/token", data={**form, "redirect_uri": BASE + "/evil"})
        check("exchange redirect binding", r.status_code == 400)
        r = await browser.post("/token", data=form)
        check("code exchange", r.status_code == 200 and r.json().get("token_type") == "Bearer"
              and "no-store" in r.headers.get("cache-control", ""))
        token = r.json()["access_token"]
        r = await browser.post("/token", data=form)
        check("code replay", r.status_code == 400 and r.json()["error"] == "invalid_grant")

        async def on_request(request):
            # Never save Authorization, cookies, login/code/token traffic.
            if request.method == "POST" and request.url.path == "/mcp":
                wire.append({"request": json.loads(request.content),
                             "headers": {k: v for k, v in request.headers.items() if k.startswith("mcp-")}})

        async def on_response(response):
            if response.request.method == "POST" and response.request.url.path == "/mcp":
                raw = await response.aread()
                data = json.loads(raw) if "application/json" in response.headers.get("content-type", "") else raw.decode()
                wire[-1].update({"status": response.status_code, "response": data,
                                "session_header": response.headers.get("mcp-session-id")})

        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token},
                  timeout=httpx2.Timeout(15, read=30), event_hooks={"request": [on_request], "response": [on_response]}) as http:
            async with Client(streamable_http_client(RESOURCE, http_client=http), mode="2026-07-28") as client:
                check("strict protocol pin", client.protocol_version == "2026-07-28", version=client.protocol_version)
                tools = await client.list_tools()
                check("list typed tool", [t.name for t in tools.tools] == ["g0_cit"] and tools.tools[0].output_schema is not None)
                result = await client.call_tool("g0_cit", {"revenue": 50_000_000_000, "cost": 38_000_000_000})
                check("original calculator via HTTP", not result.is_error and result.structured_content["cit_with_incentive_VND"] == 2_400_000_000,
                      output=result.structured_content)
                result = await client.call_tool("g0_cit", {"revenue": -1, "cost": 0})
                check("invalid input rejected", result.is_error)

        valid_call = next(row for row in wire if row["request"]["method"] == "tools/call")
        meta = valid_call["request"]["params"]["_meta"]
        headers = {**valid_call["headers"], "Authorization": "Bearer " + token,
                   "Accept": "application/json, text/event-stream"}
        payload = valid_call["request"]
        for bad, overrides in fixtures.items():
            r = await browser.post("/mcp", json=payload, headers={**headers, "Authorization": "Bearer " + bad})
            expected = 403 if "scope" in overrides else 401
            # SDK may use 403 for a token bound to the wrong resource.
            allowed = {401, 403} if "resource" in overrides else {expected}
            check("reject fixture " + next(iter(overrides)), r.status_code in allowed, status=r.status_code)
        discover = {"jsonrpc": "2.0", "id": 50, "method": "server/discover", "params": {"_meta": meta}}
        dh = {"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream",
              "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"}
        r = await browser.post("/mcp", json=discover, headers=dh)
        check("modern discovery", r.status_code == 200 and "result" in r.json(), response=r.json())
        r = await browser.post("/mcp", json=payload, headers={**headers, "mcp-method": "tools/list"})
        check("header mismatch", r.status_code == 400 and r.json()["error"]["code"] == -32020, status=r.status_code)
        wrong_version = json.loads(json.dumps(payload))
        wrong_version["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2099-01-01"
        r = await browser.post("/mcp", json=wrong_version, headers={**headers, "mcp-protocol-version": "2099-01-01"})
        check("unsupported version", r.status_code == 400 and r.json()["error"]["code"] == -32022, status=r.status_code, response=r.json())
        r = await browser.post("/mcp", json=payload, headers={**headers, "Origin": "https://evil.invalid"})
        check("origin rejected", r.status_code == 403)
        r = await browser.post("/mcp", json=payload, headers={**headers, "Host": "evil.invalid"})
        check("host rejected", r.status_code == 421)
        check("no legacy initialize/session", all(row["request"]["method"] != "initialize" and row.get("session_header") is None for row in wire))
        check("modern result discriminator", valid_call["response"]["result"]["resultType"] == "complete")
        check("modern metadata and mirrors", meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
              and "io.modelcontextprotocol/clientCapabilities" in meta
              and valid_call["headers"]["mcp-protocol-version"] == "2026-07-28"
              and valid_call["headers"]["mcp-method"] == "tools/call"
              and valid_call["headers"]["mcp-name"] == "g0_cit")
    return {"passed": True, "transport": "real TCP 127.0.0.1, separate uvicorn process, no ASGI TestClient",
            "versions": {n: importlib.metadata.version(n) for n in ("mcp", "Authlib", "fastapi", "httpx2")},
            "checks": checks, "wire": wire, "unverified": ["production DB/refresh/revocation/consent/rate limits", "cloud hosts", "TLS/proxy"]}


def main():
    password = secrets.token_urlsafe(32)
    fixtures = {secrets.token_urlsafe(32): override for override in (
        {"expires_at": 1}, {"resource": BASE + "/wrong"}, {"workspace_id": "g0-workspace-b"}, {"scope": "other:scope"})}
    process = multiprocessing.get_context("spawn").Process(target=serve, args=(password, fixtures))
    process.start()
    try:
        result = asyncio.run(smoke(password, fixtures))
        # Prove fixture secrets are absent from the persisted evidence.
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        assert password not in encoded and all(t not in encoded for t in fixtures)
        (OUT / "wire-auth.json").write_text(encoded + "\n", encoding="utf-8")
        print(json.dumps({"passed": True, "checks": len(result["checks"])}))
    finally:
        process.terminate()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()


if __name__ == "__main__": main()
