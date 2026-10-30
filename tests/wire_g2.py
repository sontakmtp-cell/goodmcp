"""Real HTTP/OAuth/MCP acceptance, run sharing Caddy's loopback network namespace.

Only sanitized MCP traffic/statuses are printed. Passwords, login cookies, codes
and access/refresh values stay in memory or /wirestate (private test-only volume).
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

import httpx
import httpx2
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

BASE = os.environ["HUB_PUBLIC_BASE_URL"].rstrip("/")
ISSUER, RESOURCE = BASE + "/auth", BASE + "/mcp"
CALLBACK = "http://127.0.0.1:8766/callback"
REVOKED_WORKSPACE = "20000000-0000-4000-8000-000000000099"
STATE = Path("/wirestate/state.json")
PASSWORD = Path("/run/secrets/owner_password").read_text().strip()
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "goodmcp-g2-conformance", "version": "1"}}
checks, wire, secret_values = [], [], [PASSWORD]


def check(name, condition, **details):
    checks.append({"name": name, "passed": bool(condition), **details})
    if not condition: raise AssertionError(name)


def csrf(response):
    match = re.search(r'name="csrf"[^>]*value="([^"\s]+)"', response.text)
    if not match: raise AssertionError("CSRF field missing; status=" + str(response.status_code))
    return html.unescape(match[1])


def code_from(response, state):
    fields = parse_qs(urlsplit(response.headers.get("location", "")).query)
    check("state and issuer bound response", response.status_code == 302 and fields.get("state") == [state] and fields.get("iss") == [ISSUER])
    code = fields["code"][0]
    secret_values.append(code)
    return code


def rpc(token, method="tools/call", arguments=None, *, headers=None, path="/mcp", meta=None):
    body = {"jsonrpc": "2.0", "id": 42, "method": method, "params": {"_meta": meta or META}}
    h = {"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if method == "tools/call":
        body["params"].update({"name": "hub_get_workspace", "arguments": arguments or {"workspace_id": stored_workspace}})
        h["Mcp-Name"] = "hub_get_workspace"
    h.update(headers or {})
    return httpx.post(BASE + path, json=body, headers=h, timeout=15)


def full():
    global stored_workspace
    browser = httpx.Client(base_url=BASE, timeout=15)
    md = browser.get("/.well-known/oauth-authorization-server/auth")
    check("AS discovery", md.status_code == 200 and md.json()["issuer"] == ISSUER and md.json()["code_challenge_methods_supported"] == ["S256"])
    check("AS alias discovery", browser.get("/auth/.well-known/oauth-authorization-server").json() == md.json())
    missing = browser.post("/mcp", json={})
    check("missing token challenge", missing.status_code == 401 and "resource_metadata=" in missing.headers.get("www-authenticate", ""))
    resource = browser.get("/.well-known/oauth-protected-resource/mcp")
    check("resource discovery", resource.status_code == 200 and resource.json()["resource"] == RESOURCE and resource.json()["authorization_servers"] == [ISSUER])
    registration = {"client_name": "G2 wire readonly", "redirect_uris": [CALLBACK], "scope": "hub:read projects:read"}
    r = browser.post("/auth/register", json=registration)
    check("DCR public client", r.status_code == 201 and r.json()["token_endpoint_auth_method"] == "none")
    client_id = r.json()["client_id"]
    other_client = browser.post("/auth/register", json={**registration, "client_name": "Other client"}).json()["client_id"]
    r = browser.post("/auth/register", json={**registration, "redirect_uris": ["javascript:alert(1)"]})
    check("DCR unsafe redirect rejected", r.status_code == 400)
    r = browser.post("/auth/register", json={**registration, "scope": "admin:all"})
    check("DCR unsupported scope rejected", r.status_code == 400)
    r = browser.post("/auth/login", data={"email": "owner@local.invalid", "password": PASSWORD, "csrf": "wrong"})
    check("login CSRF", r.status_code == 403)
    r = browser.get("/auth/login")
    check("HttpOnly SameSite cookie", "httponly" in r.headers.get("set-cookie", "").lower() and "samesite=lax" in r.headers.get("set-cookie", "").lower())
    check("local HTTP cookie exception", "secure;" not in r.headers.get("set-cookie", "").lower())
    old_cookie = browser.cookies.get("hub_session")
    r = browser.post("/auth/login", data={"email": "owner@local.invalid", "password": "wrong", "csrf": csrf(r)})
    check("wrong password", r.status_code == 401)
    r = browser.get("/auth/login")
    old_cookie = browser.cookies.get("hub_session")
    r = browser.post("/auth/login", data={"email": "owner@local.invalid", "password": PASSWORD, "csrf": csrf(r)})
    check("owner login and session fixation protection", r.status_code == 303 and browser.cookies.get("hub_session") != old_cookie)
    secret_values.append(browser.cookies.get("hub_session"))

    def authorization(**overrides):
        verifier = secrets.token_urlsafe(48)
        params = {"response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK,
                  "scope": "hub:read", "resource": RESOURCE, "state": secrets.token_urlsafe(24),
                  "code_challenge": create_s256_code_challenge(verifier), "code_challenge_method": "S256"}
        params.update(overrides)
        return params, verifier, browser.get("/auth/authorize", params=params)

    params, verifier, consent = authorization()
    check("explicit consent required", consent.status_code == 200 and "location" not in consent.headers)
    options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', consent.text)
    stored_workspace = next(value for value, label in options if "G2 revoked fixture" not in label)
    check("fixture isolated workspace present", any(value == REVOKED_WORKSPACE for value, label in options))
    r = browser.post("/auth/authorize", data={"csrf": "wrong", "workspace_id": stored_workspace, "consent": "allow"})
    check("consent CSRF", r.status_code == 403)
    r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "consent": "allow"})
    check("consent workspace membership", r.status_code == 403)
    for name, override in (
        ("redirect exact match", {"redirect_uri": CALLBACK + "/wrong"}),
        ("PKCE S256 only", {"code_challenge_method": "plain"}),
        ("PKCE mandatory", {"code_challenge": ""}),
        ("resource mandatory", {"resource": "https://wrong.invalid/mcp"}),
        ("scope escalation denied", {"scope": "projects:write"}),
    ):
        _, _, r = authorization(**override)
        check(name, r.status_code == 400 and "location" not in r.headers)

    def mint(*, workspace=None, scope="hub:read"):
        params, verifier, consent = authorization(scope=scope)
        r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": workspace or stored_workspace, "consent": "allow"})
        code = code_from(r, params["state"])
        form = {"grant_type": "authorization_code", "client_id": client_id, "code": code, "redirect_uri": CALLBACK,
                "code_verifier": verifier, "resource": RESOURCE}
        r = browser.post("/auth/token", data=form)
        check("code exchanged", r.status_code == 200 and "refresh_token" in r.json())
        result = r.json()
        secret_values.extend([result["access_token"], result["refresh_token"]])
        return result, form

    params, verifier, consent = authorization()
    r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": stored_workspace, "consent": "deny"})
    check("consent denied", r.status_code == 302 and parse_qs(urlsplit(r.headers["location"]).query).get("error") == ["access_denied"])
    params, verifier, consent = authorization()
    r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": stored_workspace, "consent": "allow"})
    code = code_from(r, params["state"])
    r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": stored_workspace, "consent": "allow"})
    check("consent form replay rejected", r.status_code == 403)
    form = {"grant_type": "authorization_code", "client_id": client_id, "code": code, "redirect_uri": CALLBACK,
            "code_verifier": verifier, "resource": RESOURCE}
    for name, override in (("wrong PKCE verifier", {"code_verifier": "w" * 64}),
                           ("code client binding", {"client_id": other_client}),
                           ("code redirect binding", {"redirect_uri": CALLBACK + "/wrong"}),
                           ("token audience binding", {"resource": "https://wrong.invalid/mcp"})):
        r = browser.post("/auth/token", data={**form, **override})
        check(name, r.status_code == 400)
    r = browser.post("/auth/token", data=form)
    check("valid code after bad attempts", r.status_code == 200)
    first = r.json()
    secret_values.extend([first["access_token"], first["refresh_token"]])
    check("code token initially usable", rpc(first["access_token"]).status_code == 200)
    r = browser.post("/auth/token", data=form)
    check("code replay rejected", r.status_code == 400 and r.json()["error"] == "invalid_grant")
    check("code replay revokes issued family", rpc(first["access_token"]).status_code == 401)

    tokens, _ = mint()
    async def sdk_wire():
        async def sent(request):
            if request.method == "POST" and request.url.path == "/mcp":
                wire.append({"request": json.loads(request.content), "headers": {k: v for k, v in request.headers.items() if k.startswith("mcp-")}})
        async def received(response):
            if response.request.method == "POST" and response.request.url.path == "/mcp":
                body = await response.aread()
                wire[-1].update({"status": response.status_code, "session_header": response.headers.get("mcp-session-id"), "response": json.loads(body)})
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + tokens["access_token"]}, timeout=15,
                event_hooks={"request": [sent], "response": [received]}) as http:
            async with Client(streamable_http_client(RESOURCE, http_client=http), mode="2026-07-28") as client:
                check("SDK pin", client.protocol_version == "2026-07-28")
                tools = await client.list_tools()
                check("readonly tool catalog only", [t.name for t in tools.tools] == ["hub_get_workspace"] and tools.tools[0].annotations.read_only_hint)
                result = await client.call_tool("hub_get_workspace", {"workspace_id": stored_workspace})
                check("authenticated tenant tool", not result.is_error and result.structured_content["workspace_id"] == stored_workspace)
                result = await client.call_tool("hub_get_workspace", {"workspace_id": REVOKED_WORKSPACE})
                check("no cross-workspace tool", result.is_error)
                result = await client.call_tool("hub_get_workspace", {"workspace_id": "bad"})
                check("invalid input schema", result.is_error)
    asyncio.run(sdk_wire())
    successful = next(r for r in wire if r["request"]["method"] == "tools/call" and not r["response"]["result"].get("isError"))
    listed = next(r for r in wire if r["request"]["method"] == "tools/list")
    check("private catalog cache", listed["response"]["result"]["cacheScope"] == "private")
    check("modern wire complete", successful["response"]["result"]["resultType"] == "complete")
    check("modern metadata headers", successful["headers"]["mcp-protocol-version"] == "2026-07-28" and successful["headers"]["mcp-name"] == "hub_get_workspace"
          and "io.modelcontextprotocol/clientCapabilities" in successful["request"]["params"]["_meta"])
    check("no legacy handshake or session", all(r["request"]["method"] != "initialize" and r["session_header"] is None for r in wire))
    r = rpc(tokens["access_token"], "server/discover")
    check("modern discovery", r.status_code == 200 and "result" in r.json(), response=r.json())
    r = rpc(tokens["access_token"], headers={"Mcp-Method": "tools/list"})
    check("mirror header mismatch", r.status_code == 400 and r.json()["error"]["code"] == -32020)
    r = rpc(tokens["access_token"], meta={**META, "io.modelcontextprotocol/protocolVersion": "2099-01-01"}, headers={"MCP-Protocol-Version": "2099-01-01"})
    check("unsupported protocol rejected", r.status_code == 400 and r.json()["error"]["code"] == -32022)
    r = browser.post("/mcp", headers={"Authorization": "Bearer " + tokens["access_token"]}, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("legacy disabled explicitly", r.status_code == 400)
    for path in ("/mcp", "/mcp/", "/mcp//", "/api/v1/me/workspaces", "/api/v1/unknown"):
        r = browser.post(path, json={})
        check("no anonymous alias " + path, r.status_code == 401)
    check("wrong workspace selection", rpc(tokens["access_token"], headers={"X-Workspace-ID": REVOKED_WORKSPACE}).status_code == 403)
    check("host allowlist", rpc(tokens["access_token"], headers={"Host": "evil.invalid"}).status_code == 421)
    check("origin allowlist", rpc(tokens["access_token"], headers={"Origin": "https://evil.invalid"}).status_code == 403)
    check("legacy GET stream disabled", browser.get("/mcp", headers={"Authorization": "Bearer " + tokens["access_token"]}).status_code == 405)
    read_api = browser.get("/api/v1/me/workspaces", headers={"Authorization": "Bearer " + tokens["access_token"]})
    check("REST identity from token", read_api.status_code == 200 and read_api.json()["data"][0]["workspace_id"] == stored_workspace)
    evaluator = run_evaluator(tokens["access_token"], stored_workspace, read_api.json()["data"][0])

    def refresh(values, **overrides):
        return browser.post("/auth/token", data={"grant_type": "refresh_token", "client_id": client_id,
            "refresh_token": values["refresh_token"], "resource": RESOURCE, **overrides})
    r = refresh(tokens, client_id=other_client)
    check("refresh client binding", r.status_code == 400)
    r = refresh(tokens, scope="projects:write")
    check("refresh cannot escalate scope", r.status_code == 400)
    r = refresh(tokens)
    check("refresh rotates", r.status_code == 200 and r.json()["refresh_token"] != tokens["refresh_token"])
    rotated = r.json()
    secret_values.extend([rotated["access_token"], rotated["refresh_token"]])
    check("new access accepted", rpc(rotated["access_token"]).status_code == 200)
    r = refresh(tokens)
    check("refresh replay rejected", r.status_code == 400 and r.json()["error"] == "invalid_grant")
    check("refresh replay revokes new access", rpc(rotated["access_token"]).status_code == 401)
    check("refresh replay revokes descendant refresh", refresh(rotated).status_code == 400)
    revoke_tokens, _ = mint()
    r = browser.post("/auth/revoke", data={"client_id": other_client, "token": revoke_tokens["access_token"]})
    check("revocation client binding", r.status_code == 400)
    check("wrong-client revocation does not revoke", rpc(revoke_tokens["access_token"]).status_code == 200)
    r = browser.post("/auth/revoke", data={"client_id": client_id, "token": revoke_tokens["refresh_token"]})
    check("revoke family", r.status_code == 200 and rpc(revoke_tokens["access_token"]).status_code == 401)
    check("revoked refresh denied", refresh(revoke_tokens).status_code == 400)
    check("unknown revoke non-enumerating", browser.post("/auth/revoke", data={"client_id": client_id, "token": "unknown"}).status_code == 200)

    # Two simultaneous exchanges of the same credential must never both issue tokens.
    race, _ = mint()
    request_body = {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": race["refresh_token"], "resource": RESOURCE}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: httpx.post(ISSUER + "/token", data=request_body, timeout=20), range(2)))
    check("concurrent refresh serialized", sorted(r.status_code for r in replies) == [200, 400])
    winner = next(r.json() for r in replies if r.status_code == 200)
    secret_values.extend([winner["access_token"], winner["refresh_token"]])
    check("concurrent replay revokes winning family", rpc(winner["access_token"]).status_code == 401)

    params, verifier, consent = authorization()
    r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": stored_workspace, "consent": "allow"})
    race_code = code_from(r, params["state"])
    code_body = {"grant_type": "authorization_code", "client_id": client_id, "code": race_code,
                 "redirect_uri": CALLBACK, "code_verifier": verifier, "resource": RESOURCE}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: httpx.post(ISSUER + "/token", data=code_body, timeout=20), range(2)))
    check("concurrent code exchange serialized", sorted(r.status_code for r in replies) == [200, 400])
    winner = next(r.json() for r in replies if r.status_code == 200)
    secret_values.extend([winner["access_token"], winner["refresh_token"]])
    check("concurrent code replay revokes issued access", rpc(winner["access_token"]).status_code == 401)
    stepped, _ = mint(scope="hub:read projects:read")
    check("scope step-up requires fresh consent", set(stepped["scope"].split()) == {"hub:read", "projects:read"})
    r = browser.post("/auth/token", data={"grant_type": "password", "client_id": client_id, "resource": RESOURCE})
    check("password grant disabled", r.status_code == 400)

    negative = {name: mint(workspace=REVOKED_WORKSPACE if name == "workspace" else None)[0]
                for name in ("expired", "audience", "issuer", "scope", "workspace")}
    persisted, _ = mint()
    params, verifier, consent = authorization()
    r = browser.post("/auth/authorize", data={"csrf": csrf(consent), "workspace_id": stored_workspace, "consent": "allow"})
    pending_code = code_from(r, params["state"])
    state = {"workspace_id": stored_workspace, "client_id": client_id, "persisted": persisted,
             "negative_tokens": negative, "cookie": browser.cookies.get("hub_session"),
             "pending_exchange": {"grant_type": "authorization_code", "client_id": client_id, "code": pending_code,
                 "redirect_uri": CALLBACK, "code_verifier": verifier, "resource": RESOURCE}}
    STATE.write_text(json.dumps(state), encoding="utf-8")
    STATE.chmod(0o600)
    secret_values.extend([v for pair in negative.values() for k, v in pair.items() if k.endswith("token")])

    # Login throttling is durable; run after all owner logins so it cannot poison other fixtures.
    for i in range(6):
        r = browser.get("/auth/login")
        r = browser.post("/auth/login", data={"csrf": csrf(r), "email": "throttle@fixture.invalid", "password": "wrong"})
    check("login rate limit", r.status_code == 429)
    browser.close()
    return {"evaluator": evaluator}


def run_evaluator(token, workspace, expected):
    connection = {"transport": "streamable-http", "url": RESOURCE, "protocol": "2026-07-28", "headers_env": {"Authorization": "G2_EVALUATOR_BEARER"}}
    cases = [{"id": "workspace-exact", "tool": "hub_get_workspace", "arguments": {"workspace_id": workspace}, "expect": {"structured_content": expected}},
             {"id": "wrong-workspace", "tool": "hub_get_workspace", "arguments": {"workspace_id": REVOKED_WORKSPACE}, "expect": {"is_error": True}}]
    Path("/wirestate/connection.json").write_text(json.dumps(connection))
    Path("/wirestate/cases.json").write_text(json.dumps(cases))
    result = subprocess.run([sys.executable, "tests/mcp_evaluation/evaluation.py", "--connection", "/wirestate/connection.json", "--cases", "/wirestate/cases.json", "--output", "/wirestate/evaluator.json"],
        env={**os.environ, "G2_EVALUATOR_BEARER": "Bearer " + token}, capture_output=True, text=True, timeout=30)
    check("independent deterministic evaluator", result.returncode == 0)
    report = json.loads(Path("/wirestate/evaluator.json").read_text())
    check("evaluator fixtures passed", report["passed"] and report["observed_protocol"] == "2026-07-28")
    return report


def negatives(state):
    global stored_workspace
    stored_workspace = state["workspace_id"]
    for name, token in state["negative_tokens"].items():
        r = rpc(token["access_token"])
        expected = 403 if name == "scope" else 401
        check("reject " + name, r.status_code == expected, status=r.status_code)


def resume(state):
    global stored_workspace
    stored_workspace = state["workspace_id"]
    response = rpc(state["persisted"]["access_token"])
    check("access survives API/issuer restart", response.status_code == 200, status=response.status_code)
    r = httpx.post(ISSUER + "/token", data=state["pending_exchange"], timeout=15)
    check("unconsumed code survives restart", r.status_code == 200)
    r = httpx.post(ISSUER + "/token", data={"grant_type": "refresh_token", "client_id": state["client_id"],
        "resource": RESOURCE, "refresh_token": state["persisted"]["refresh_token"]}, timeout=15)
    check("refresh survives restart", r.status_code == 200)
    with httpx.Client(base_url=BASE, cookies={"hub_session": state["cookie"]}) as browser:
        r = browser.get("/auth/account")
        check("login session survives restart", r.status_code == 200)
        r = browser.post("/auth/logout", data={"csrf": csrf(r)})
        check("logout deletes session", r.status_code == 303 and browser.get("/auth/account").status_code == 303)


if __name__ == "__main__":
    phase = sys.argv[1]
    try:
        extra = full() if phase == "full" else (negatives if phase == "negatives" else resume)(json.loads(STATE.read_text()))
        result = {"phase": phase, "passed": True, "checks": checks, "wire": wire, **(extra or {})}
        encoded = json.dumps(result, ensure_ascii=True)
        assert all(value not in encoded for value in secret_values if len(value) > 20)
        print(encoded)
    except Exception as error:
        print(json.dumps({"phase": phase, "passed": False, "checks": checks, "failure": str(error)[:200]}, ensure_ascii=True))
        raise SystemExit(1)
