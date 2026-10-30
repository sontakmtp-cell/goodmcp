import base64
import hashlib
import socket
from unittest.mock import Mock

import pytest
from goodmcp.auth_config import AuthSettings
from goodmcp.oauth_clients import validate_metadata, fetch_cimd, public_addresses, PinnedHTTPSConnection
from goodmcp.passwords import password_hash, verify_password


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1", "192.168.1.1", "::ffff:127.0.0.1", "224.0.0.1", "2002:c0a8:101::"])
def test_cimd_rejects_private_dns(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))])
    with pytest.raises(ValueError): public_addresses("example.com")


@pytest.mark.parametrize("url", ["http://example.com/client.json", "https://user:password@example.com/client.json", "https://example.com:8443/client.json", "https://example.com/client.json#fragment", "https://example.com/client.json?next=private"])
def test_cimd_rejects_unsafe_url_without_fetch(url):
    with pytest.raises(ValueError): fetch_cimd(url)


def test_cimd_pins_public_dns_and_refuses_redirect(monkeypatch):
    import goodmcp.oauth_clients as module
    monkeypatch.setattr(module, "public_addresses", lambda h: ["93.184.216.34"])
    fake = Mock()
    fake.getresponse.return_value.status = 302
    constructor = Mock(return_value=fake)
    monkeypatch.setattr(module, "PinnedHTTPSConnection", constructor)
    with pytest.raises(ValueError): fetch_cimd("https://example.com/client.json")
    constructor.assert_called_once_with("example.com", "93.184.216.34")
    fake.close.assert_called_once()


def test_cimd_tls_connect_uses_pinned_ip_and_original_sni(monkeypatch):
    sock = Mock()
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=sock))
    c = PinnedHTTPSConnection("example.com", "93.184.216.34")
    assert c._context.check_hostname and c._context.verify_mode == 2
    c._context = Mock()
    c.connect()
    socket.create_connection.assert_called_once_with(("93.184.216.34", 443), 3)
    c._context.wrap_socket.assert_called_once_with(sock, server_hostname="example.com")


@pytest.mark.parametrize("body", [b"x" * 65537, b'{"client_id":"https://different.example/client.json"}'])
def test_cimd_size_and_client_id_binding(monkeypatch, body):
    import goodmcp.oauth_clients as module
    monkeypatch.setattr(module, "public_addresses", lambda h: ["93.184.216.34"])
    fake = Mock()
    response = fake.getresponse.return_value
    response.status = 200
    response.getheader.side_effect = lambda name, default=None: "application/json" if name == "Content-Type" else default
    blocks = [body[i:i+8192] for i in range(0, len(body), 8192)] + [b""]
    response.read1.side_effect = blocks
    monkeypatch.setattr(module, "PinnedHTTPSConnection", lambda *a: fake)
    with pytest.raises(ValueError): fetch_cimd("https://example.com/client.json")


def test_argon2_and_valid_legacy_upgrade_check():
    value = "test-password-is-not-a-credential"
    encoded = password_hash(value)
    assert encoded.startswith("$argon2id$") and verify_password(encoded, value)
    assert not verify_password(encoded, "wrong")
    salt = b"1234567890123456"
    digest = hashlib.scrypt(value.encode(), salt=salt, n=16384, r=8, p=1)
    legacy = "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()
    assert verify_password(legacy, value) and not verify_password(legacy, "wrong")
    assert not verify_password("!no-login-fixture", value)


def test_https_settings_and_public_metadata_validation(monkeypatch):
    monkeypatch.setenv("HUB_PUBLIC_BASE_URL", "https://hub.example.com")
    assert AuthSettings.from_env().secure_cookie
    monkeypatch.setenv("HUB_PUBLIC_BASE_URL", "http://untrusted.example.com")
    monkeypatch.setenv("HUB_ALLOW_HTTP_LOOPBACK", "1")
    with pytest.raises(RuntimeError): AuthSettings.from_env()
    with pytest.raises(ValueError): validate_metadata({"redirect_uris": ["javascript:alert(1)"]}, allow_loopback=False)
    with pytest.raises(ValueError): validate_metadata({"redirect_uris": ["http://localhost/callback"]}, allow_loopback=False)
    with pytest.raises(ValueError): validate_metadata({"redirect_uris": ["https://app.example.com/callback"], "scope": "admin:all"}, allow_loopback=False)
