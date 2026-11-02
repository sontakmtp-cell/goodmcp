"""Real signatures and isolated PostgreSQL: no simulated Google success claims."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi.testclient import TestClient
from sqlalchemy import text

from goodmcp.google_oidc import validate_identity, provision, authorization_url
from goodmcp.oauth_store import AuthStore, sha
from goodmcp.auth_config import AuthSettings

CONFIG = {'client_id': 'fixture.apps.googleusercontent.com', 'client_secret': 'test-secret', 'state_key': 'x' * 48}


@pytest.mark.parametrize('change', [None, {'iss': 'https://wrong.invalid'}, {'aud': 'wrong'}, {'exp': 1},
    {'nonce': 'wrong'}, {'email_verified': False}, {'email_verified': 'true'}, {'sub': None}, {'azp': 'wrong'}])
def test_google_verifies_signed_identity(change):
    key = JsonWebKey.generate_key('RSA', 2048, is_private=True)
    claims = {'iss': 'https://accounts.google.com', 'aud': CONFIG['client_id'], 'iat': int(time.time()),
              'exp': int(time.time()) + 120, 'nonce': 'expected', 'sub': 'google-subject',
              'email': 'verified@fixture.invalid', 'email_verified': True}
    claims.update(change or {})
    token = JsonWebToken(['RS256']).encode({'alg': 'RS256'}, claims, key)
    if change is None:
        assert validate_identity(CONFIG, token, key.as_dict(is_private=False), 'expected')['sub'] == 'google-subject'
        wrong = JsonWebKey.generate_key('RSA', 2048, is_private=True)
        with pytest.raises(Exception):
            validate_identity(CONFIG, token, wrong.as_dict(is_private=False), 'expected')
    else:
        with pytest.raises(Exception):
            validate_identity(CONFIG, token, key.as_dict(is_private=False), 'expected')


@pytest.fixture
def issuer():
    if os.environ.get('HUB_TEST_AUTH') != '1':
        pytest.skip('isolated issuer database required')
    store = AuthStore(AuthSettings.from_env())
    yield store
    store.engine.dispose()


def claims(email=None, subject=None):
    return {'sub': subject or uuid4().hex, 'email': email or uuid4().hex + '@identity.fixture.invalid', 'name': 'G9 identity'}


def test_google_subject_concurrent_provision_no_email_merge(issuer):
    identity = claims()
    def create(_):
        with issuer.engine.begin() as conn:
            return provision(conn, identity, allow_signup=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(create, range(2)))
    assert ids[0] == ids[1]
    with issuer.engine.begin() as conn:
        different = provision(conn, claims(email=identity['email']), allow_signup=True)
        assert different != ids[0]
        assert len(issuer.memberships(conn, ids[0])) == 1
        assert len(issuer.memberships(conn, different)) == 1
        with pytest.raises(ValueError):
            provision(conn, claims(), allow_signup=False)


def test_google_link_requires_authenticated_owner_and_subject_unique(issuer):
    with issuer.engine.begin() as conn:
        # Each run owns its recovery fixture; never re-link an arbitrary existing
        # owner left by an earlier integration run.
        owner = conn.execute(text("INSERT INTO users(email,password_hash) VALUES(:email,'!recovery-fixture') RETURNING id"),
                             {'email': uuid4().hex + '@recovery.fixture.invalid'}).scalar_one()
        workspace = conn.execute(text("INSERT INTO workspaces(name) VALUES('Google link recovery fixture') RETURNING id")).scalar_one()
        conn.execute(text("INSERT INTO memberships(workspace_id,user_id,role) VALUES(:ws,:u,'owner')"), {'ws': workspace, 'u': owner})
        identity = claims()
        assert provision(conn, identity, link_user_id=owner) == owner
        other = provision(conn, claims(), allow_signup=True)
        with pytest.raises(ValueError):
            provision(conn, identity, link_user_id=other)
    # Disabled identities cannot be used to provision a replacement account.
    with issuer.engine.begin() as conn:
        conn.execute(text('UPDATE users SET active=false WHERE id=:u'), {'u': other})
    with issuer.engine.begin() as conn:
        row = conn.execute(text('SELECT subject,email FROM user_identities WHERE user_id=:u'), {'u': other}).mappings().one()
        with pytest.raises(ValueError):
            provision(conn, claims(subject=row['subject'], email=row['email']), allow_signup=True)


def test_web_session_csrf_logout_and_mcp_cookie_separation(issuer, monkeypatch, tmp_path):
    from apps.api.auth import app
    from apps.api.web_sessions import csrf_token
    with issuer.engine.begin() as conn:
        user = provision(conn, claims(), allow_signup=True)
        cookie, _ = issuer.new_session(conn, user)
    keyfile = tmp_path / 'internal-key'
    keyfile.write_text('k' * 48)
    monkeypatch.setenv('HUB_WEB_SESSION_KEY_FILE', str(keyfile))
    # Override service state only; no external identity provider is contacted.
    app.state.store = issuer
    base = issuer.settings.base
    with TestClient(app, base_url=base) as client:
        client.cookies.set('hub_session', cookie)
        data = client.get('/auth/web/session').json()['data']
        assert data['user']['id'] == str(user) and len(data['workspaces']) == 1
        assert data['csrf'] == csrf_token(cookie)
        assert client.post('/auth/web/select-workspace', json={'workspace_id': data['workspace_id']}).status_code == 403
        headers = {'Origin': issuer.settings.origin, 'X-CSRF-Token': data['csrf']}
        assert client.post('/auth/web/select-workspace', headers=headers, json={'workspace_id': data['workspace_id']}).status_code == 200
        assert client.post('/internal/web-session', json={'cookie': cookie, 'method': 'GET'}).status_code == 401
        assert client.post('/internal/web-session', headers={'Authorization': 'Bearer ' + 'k' * 48}, json={'cookie': cookie, 'method': 'POST'}).status_code == 403
        assert client.post('/auth/web/logout', headers=headers, json={'all_devices': True}).status_code == 200
        assert client.get('/auth/web/session').status_code == 401


def test_callback_one_use_and_wrong_state_without_google_network(issuer, monkeypatch):
    from goodmcp import google_oidc
    from goodmcp.cloudflare_sso import verify_state
    from urllib.parse import urlsplit, parse_qs
    with issuer.engine.begin() as conn:
        cookie, _ = issuer.new_session(conn)
    query = parse_qs(urlsplit(authorization_url(issuer, CONFIG, cookie)).query)
    assert query['scope'] == ['openid email profile'] and query['code_challenge_method'] == ['S256']
    state = query['state'][0]
    with pytest.raises(ValueError):
        google_oidc.finish(issuer, CONFIG, 'wrong-cookie', state, 'code')
    class NetworkFailure:
        def __init__(self, *a, **kw): pass
        def __enter__(self): raise RuntimeError('network deliberately offline')
        def __exit__(self, *a): pass
    monkeypatch.setattr(google_oidc, 'OAuth2Client', NetworkFailure)
    with pytest.raises(RuntimeError):
        google_oidc.finish(issuer, CONFIG, cookie, state, 'code')
    with pytest.raises(ValueError, match='consumed'):
        google_oidc.finish(issuer, CONFIG, cookie, state, 'code')


def test_mcp_fresh_login_uses_google_and_keeps_owner_recovery(issuer, monkeypatch):
    from apps.api.auth import app
    from goodmcp import google_oidc, cloudflare_sso
    from urllib.parse import urlsplit, parse_qs
    monkeypatch.setattr(google_oidc, 'configuration', lambda: CONFIG)
    recovery = {**CONFIG, 'issuer': 'https://fixture.cloudflareaccess.com/cdn-cgi/access/sso/oidc/recovery'}
    monkeypatch.setattr(cloudflare_sso, 'configuration', lambda: recovery)
    with TestClient(app, base_url=issuer.settings.base) as client:
        response = client.get('/auth/authorize?client_id=fixture&scope=hub%3Aread', follow_redirects=False)
        assert response.status_code == 303
        target = urlsplit(response.headers['location'])
        assert target.path == '/auth/google/start'
        assert parse_qs(target.query)['return_to'][0].startswith('/auth/authorize?')
        # Direct legacy recovery stays on the existing Cloudflare provider.
        response = client.get('/auth/login?return_to=/app/account', follow_redirects=False)
        assert response.status_code == 302
        assert response.headers['location'].startswith(recovery['issuer'] + '/authorization?')
        client.cookies.clear()
        monkeypatch.setattr(google_oidc, 'configuration', lambda: None)
        response = client.get('/auth/authorize?client_id=fixture', follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'].startswith('/auth/login?')
