"""Interactive readonly OAuth + MCP client. No model API, token files or token output.

Uses DCR, opens the user's browser for login/consent, listens on fixed loopback
callback, calls one authenticated read tool and revokes this temporary grant.
"""
import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
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
    args = parser.parse_args()
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
        registered = http.post(issuer["registration_endpoint"], json={"client_name": "Ephemeral readonly CLI", "redirect_uris": [callback], "scope": "hub:read"})
        registered.raise_for_status()
        client_id = registered.json()["client_id"]
        url = issuer["authorization_endpoint"] + "?" + urlencode({"client_id": client_id, "response_type": "code", "redirect_uri": callback,
            "resource": base + "/mcp", "scope": "hub:read", "code_challenge": create_s256_code_challenge(verifier), "code_challenge_method": "S256", "state": state})
        print("Opening browser for login and readonly consent; no password is sent to this CLI.")
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
            async def call():
                async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + tokens["access_token"]}, timeout=30) as transport:
                    async with Client(streamable_http_client(base + "/mcp", http_client=transport), mode="2026-07-28") as client:
                        answer = await client.call_tool("hub_get_workspace", {"workspace_id": ws})
                        if answer.is_error: raise RuntimeError("Tool failed")
                        print(answer.structured_content)
            asyncio.run(call())
        finally:
            revoked = http.post(issuer["revocation_endpoint"], data={"client_id": client_id, "token": tokens["refresh_token"]})
            revoked.raise_for_status()
            print("Temporary connection revoked; no token was saved.")


if __name__ == "__main__": main()
