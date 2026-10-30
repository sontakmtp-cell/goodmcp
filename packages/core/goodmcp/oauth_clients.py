"""Bounded public-client metadata and SSRF-safe CIMD. No redirects or private DNS."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import urlsplit
from .auth_config import SCOPES


def validate_redirect(value, *, allow_loopback):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r"[\x00-\x20\x7f]", value):
        raise ValueError("Invalid redirect URI")
    p = urlsplit(value)
    if p.port == 0: raise ValueError("Invalid redirect port")
    local = allow_loopback and p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost", "::1")
    if p.username or p.password or p.fragment or not p.hostname or (p.scheme != "https" and not local):
        raise ValueError("Redirect requires HTTPS (explicit loopback exception for local tests)")
    return value


def validate_metadata(data, *, allow_loopback):
    if not isinstance(data, dict): raise ValueError("Client metadata must be an object")
    redirects = data.get("redirect_uris")
    if not isinstance(redirects, list) or not 1 <= len(redirects) <= 10: raise ValueError("1-10 redirect URIs required")
    redirects = list(dict.fromkeys(validate_redirect(x, allow_loopback=allow_loopback) for x in redirects))
    name = data.get("client_name", "MCP client")
    if not isinstance(name, str) or not 1 <= len(name) <= 100: raise ValueError("Invalid client name")
    if data.get("token_endpoint_auth_method", "none") != "none": raise ValueError("Only public PKCE clients supported")
    if set(data.get("grant_types", ["authorization_code", "refresh_token"])) - {"authorization_code", "refresh_token"}:
        raise ValueError("Unsupported grant")
    if data.get("response_types", ["code"]) != ["code"]: raise ValueError("Only code response supported")
    scope = data.get("scope", "hub:read")
    if not isinstance(scope, str) or not scope.split() or set(scope.split()) - set(SCOPES): raise ValueError("Invalid scopes")
    return {"name": name, "redirect_uris": redirects, "allowed_scopes": sorted(set(scope.split()))}


def public_addresses(hostname):
    records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(r[4][0] for r in records))
    def allowed(value):
        address = ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified:
            return False
        if isinstance(address, ipaddress.IPv6Address):
            for embedded in (address.ipv4_mapped, address.sixtofour, *(address.teredo or ())):
                if embedded is not None and not allowed(str(embedded)): return False
        return True
    if not addresses or any(not allowed(value) for value in addresses):
        raise ValueError("Client metadata DNS includes a non-public address")
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, address):
        super().__init__(hostname, 443, timeout=3, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the already-validated IP, preserve the original TLS SNI/name.
        # No second DNS lookup, proxy environment or redirect can rebind the target.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
            self.tls_socket = self.sock
        except Exception:
            sock.close()
            raise


def fetch_cimd(client_id):
    if not isinstance(client_id, str) or len(client_id) > 2048 or re.search(r"[\x00-\x20\x7f]", client_id):
        raise ValueError("Invalid client metadata URL")
    p = urlsplit(client_id)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment or p.query or p.port not in (None, 443) or not p.path:
        raise ValueError("CIMD requires a public HTTPS URL on port 443, without query/fragment")
    hostname = p.hostname.encode("idna").decode("ascii")
    if ":" in hostname or "%" in hostname or not re.fullmatch(r"[A-Za-z0-9.-]+", hostname):
        raise ValueError("Invalid client metadata hostname")
    addresses = public_addresses(hostname)
    connection = PinnedHTTPSConnection(hostname, addresses[0])
    try:
        connection.request("GET", p.path, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type", "").split(";")[0].strip() not in ("application/json", "application/oauth-client-metadata+json"):
            raise ValueError("Client metadata must return JSON 200 directly")
        if response.getheader("Content-Encoding", "identity") != "identity": raise ValueError("Compressed metadata is unsupported")
        deadline, body = time.monotonic() + 5, bytearray()
        while len(body) <= 65536:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ValueError("Client metadata read deadline exceeded")
            connection.tls_socket.settimeout(min(3, remaining))
            block = response.read1(min(8192, 65537 - len(body)))
            if not block: break
            body.extend(block)
        if len(body) > 65536: raise ValueError("Client metadata exceeds 64 KiB")
        data = json.loads(body)
        if data.get("client_id") != client_id: raise ValueError("CIMD client_id mismatch")
        return data
    finally: connection.close()
