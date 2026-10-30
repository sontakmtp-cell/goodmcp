"""Interactive readonly OAuth + MCP client. No model API, token files or token output.

Uses DCR, opens the user's browser for login/consent, listens on fixed loopback
callback, calls one authenticated read tool and revokes this temporary grant.
"""
import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import json
from pathlib import Path
from uuid import UUID
import time
from urllib.parse import urlencode, parse_qs, urlsplit
import webbrowser

import httpx
import httpx2
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--import-zip", type=Path, help="Upload/validate a ZIP; requests hub:write consent")
    parser.add_argument("--resume-upload", type=UUID, help="Resume a previous upload of the same ZIP")
    parser.add_argument("--enable", action="store_true", help="Select validated version for this workspace")
    parser.add_argument("--expected-revision", type=int, default=0, help="0 for first install; current revision for an update")
    parser.add_argument('--run-tool',choices=('cit_estimate','cit_schedule','payroll_total','fct_withhold','fct_grossup','tariff','location_sim','refs_calendar','refs_odi'))
    parser.add_argument('--arguments-file',type=Path,help='JSON business arguments; no token/password')
    parser.add_argument('--installation',type=UUID,help='Choose installation; otherwise find an enabled approved binding')
    args = parser.parse_args()
    if (args.resume_upload or args.enable) and not args.import_zip: parser.error("--import-zip required")
    if args.run_tool and args.import_zip:parser.error('Choose either import or run')
    if args.run_tool and not args.arguments_file:parser.error('--arguments-file required')
    scope = 'hub:read tools:run' if args.run_tool else "hub:read hub:write" if args.import_zip else "hub:read"
    base = args.base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("Use an origin URL without credentials, path or query")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")):
        raise ValueError("HTTPS required except loopback")
    callback, result = "http://127.0.0.1:8766/callback", {}
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # Code and state must never enter access logs.
        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            valid = urlsplit(self.path).path == "/callback" and query.get("state") == [state] and query.get("iss") == [base + "/auth"]
            if valid and query.get("code"): result["code"] = query["code"][0]
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(("Đã nhận phản hồi. Quay lại cửa sổ lệnh." if valid else "Phản hồi không hợp lệ.").encode())
            if valid and query.get("error"): result["error"] = query["error"][0]

    with HTTPServer(("127.0.0.1", 8766), Callback) as server, httpx.Client(timeout=15) as http:
        metadata = http.get(base + "/.well-known/oauth-authorization-server/auth")
        metadata.raise_for_status()
        issuer = metadata.json()
        if issuer["issuer"] != base + "/auth": raise RuntimeError("Issuer mismatch")
        for key in ("registration_endpoint", "authorization_endpoint", "token_endpoint", "revocation_endpoint"):
            if not issuer[key].startswith(base + "/auth/"): raise RuntimeError("Unexpected endpoint origin")
        registered = http.post(issuer["registration_endpoint"], json={"client_name": "Ephemeral local CLI", "redirect_uris": [callback], "scope": scope})
        registered.raise_for_status()
        client_id = registered.json()["client_id"]
        url = issuer["authorization_endpoint"] + "?" + urlencode({"client_id": client_id, "response_type": "code", "redirect_uri": callback,
            "resource": base + "/mcp", "scope": scope, "code_challenge": create_s256_code_challenge(verifier), "code_challenge_method": "S256", "state": state})
        print("Opening browser for login and consent (" + scope + "); no password is sent to this CLI.")
        webbrowser.open(url)
        server.timeout = 1
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline: server.handle_request()
        if not result.get("code"): raise RuntimeError("Consent was denied or callback timed out")
        response = http.post(issuer["token_endpoint"], data={"grant_type": "authorization_code", "client_id": client_id,
            "redirect_uri": callback, "code": result["code"], "code_verifier": verifier, "resource": base + "/mcp"})
        response.raise_for_status()
        tokens = response.json()
        try:
            workspace = http.get(base + "/api/v1/me/workspaces", headers={"Authorization": "Bearer " + tokens["access_token"]})
            workspace.raise_for_status()
            ws = workspace.json()["data"][0]["workspace_id"]
            if args.import_zip:
                from import_plugin import upload_plugin
                def request(method, path, **kwargs):
                    headers = kwargs.pop("headers", {})
                    answer = http.request(method, base + path, headers={"Authorization":"Bearer " + tokens["access_token"], **headers}, timeout=60, **kwargs)
                    if answer.status_code == 401:
                        refreshed = http.post(issuer["token_endpoint"], data={"grant_type":"refresh_token","client_id":client_id,
                            "refresh_token":tokens["refresh_token"],"resource":base + "/mcp"})
                        refreshed.raise_for_status(); tokens.update(refreshed.json())
                        answer = http.request(method, base + path, headers={"Authorization":"Bearer " + tokens["access_token"], **headers}, timeout=60, **kwargs)
                    return answer
                print(json.dumps(upload_plugin(request, ws, args.import_zip, upload_id=args.resume_upload,
                    enable=args.enable, expected_revision=args.expected_revision), ensure_ascii=False))
            async def call():
                async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + tokens["access_token"]}, timeout=30) as transport:
                    async with Client(streamable_http_client(base + "/mcp", http_client=transport), mode="2026-07-28") as client:
                        answer = await client.call_tool("hub_get_workspace", {"workspace_id": ws})
                        if answer.is_error: raise RuntimeError("Tool failed")
                        print(answer.structured_content)
                        if args.run_tool:
                            name='finance_'+args.run_tool
                            prefix=base+'/api/v1/workspaces/'+ws
                            headers={'Authorization':'Bearer '+tokens['access_token']}
                            candidates=[{'installation_id':str(args.installation),'enabled':True}] if args.installation else http.get(prefix+'/plugins',headers=headers).json()['data']['items']
                            selected=None
                            for candidate in candidates:
                                if not candidate['enabled']:continue
                                response=http.get(prefix+'/installations/'+candidate['installation_id']+'/bindings',headers=headers)
                                response.raise_for_status()
                                if any(b['mcp_name']==name for b in response.json()['data']):selected=candidate['installation_id'];break
                            if selected is None:raise RuntimeError('No enabled approved binding; run local.py runtime first')
                            parameters=json.loads(args.arguments_file.read_text(encoding='utf8'))
                            answer=await client.call_tool(name,{'installation_id':selected,'arguments':parameters,'idempotency_key':secrets.token_hex(24)})
                            if answer.is_error:raise RuntimeError('Python invocation rejected')
                            job=answer.structured_content['job'];print('Job handle: '+job['id'])
                            until=time.monotonic()+180
                            while job['state'] in ('queued','running') and time.monotonic()<until:
                                await asyncio.sleep(0.3)
                                answer=await client.call_tool('hub_get_job',{'job_id':job['id']})
                                if answer.is_error:raise RuntimeError('Job lookup rejected')
                                job=answer.structured_content['job']
                            print(json.dumps(job,ensure_ascii=False))
                            if job['state']!='succeeded':raise RuntimeError('Job did not succeed; use the reported job handle')
            asyncio.run(call())
        finally:
            revoked = http.post(issuer["revocation_endpoint"], data={"client_id": client_id, "token": tokens["refresh_token"]})
            revoked.raise_for_status()
            print("Temporary connection revoked; no token was saved.")


if __name__ == "__main__": main()
