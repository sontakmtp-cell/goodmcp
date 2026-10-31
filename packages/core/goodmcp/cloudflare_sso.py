"""Optional Cloudflare Access OIDC sign-in; Hub retains workspace consent/grants.

No user provisioning or trusted-header login. State is bound to the HttpOnly Hub
cookie and expires in five minutes; consuming the anonymous DB session prevents
callback replay. Only a preconfigured existing owner identity can sign in.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from authlib.jose import JsonWebToken
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy import text


def configuration():
    filename = os.environ.get('HUB_OIDC_CONFIG_FILE')
    if not filename:
        return None
    config = json.loads(Path(filename).read_text())
    parsed = urlsplit(config['issuer'])
    if parsed.scheme != 'https' or not parsed.hostname.endswith('.cloudflareaccess.com') or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('Invalid Cloudflare issuer')
    if len(config['state_key']) < 43 or not config['client_id'] or not config['client_secret']:
        raise ValueError('Incomplete OIDC configuration')
    return config


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def sign_state(config, cookie, *, timestamp=None):
    payload = encode(json.dumps({'cookie': hashlib.sha256(cookie.encode()).hexdigest(),
        'nonce': secrets.token_urlsafe(24), 'expires': int(time.time() if timestamp is None else timestamp) + 300},
        sort_keys=True, separators=(',', ':')).encode())
    mac = encode(hmac.digest(config['state_key'].encode(), payload.encode(), 'sha256'))
    return payload + '.' + mac


def verify_state(config, cookie, state, *, timestamp=None):
    if not cookie or not isinstance(state, str) or len(state) > 1024:
        raise ValueError('Invalid SSO state')
    payload, signature = state.split('.')
    expected = encode(hmac.digest(config['state_key'].encode(), payload.encode(), 'sha256'))
    if not hmac.compare_digest(signature, expected):
        raise ValueError('Invalid SSO signature')
    value = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    now = int(time.time() if timestamp is None else timestamp)
    if not now < value['expires'] <= now + 300 or not hmac.compare_digest(value['cookie'], hashlib.sha256(cookie.encode()).hexdigest()):
        raise ValueError('Expired or unbound SSO state')
    return value


def verifier(config, state):
    return encode(hmac.digest(config['state_key'].encode(), ('pkce:' + state).encode(), 'sha256'))


def authorization_url(config, cookie, callback):
    state = sign_state(config, cookie)
    nonce = verify_state(config, cookie, state)['nonce']
    challenge = encode(hashlib.sha256(verifier(config, state).encode()).digest())
    return config['issuer'] + '/authorization?' + urlencode({'client_id': config['client_id'],
        'redirect_uri': callback, 'response_type': 'code', 'scope': 'openid email', 'state': state,
        'nonce': nonce, 'code_challenge_method': 'S256', 'code_challenge': challenge})


def validate_identity(config, encoded_token, jwks, nonce):
    claims = JsonWebToken(['RS256']).decode(encoded_token, jwks, claims_options={
        'iss': {'essential': True, 'value': config['issuer']},
        'aud': {'essential': True, 'value': config['client_id']},
        'exp': {'essential': True}, 'iat': {'essential': True},
        'sub': {'essential': True}, 'nonce': {'essential': True, 'value': nonce},
        'email': {'essential': True, 'value': config['allowed_email']}})
    claims.validate(leeway=30)
    if claims.get('email_verified') is False:
        raise ValueError('Unverified OIDC email')
    return claims


def finish(store, config, cookie, state, code):
    bound = verify_state(config, cookie, state)
    if not code or len(code) > 4096:
        raise ValueError('Invalid SSO code')
    with store.engine.begin() as conn:
        session = store.session(conn, cookie, lock=True)
        if session is None or session['user_id'] is not None:
            raise ValueError('SSO session missing or already consumed')
        # Token endpoint and JWKS URL are derived from the fixed configured issuer.
        # No redirects or URL input from the browser/token are followed.
        with OAuth2Client(config['client_id'], config['client_secret'],
                          token_endpoint_auth_method='client_secret_basic', timeout=10, follow_redirects=False) as oauth:
            token = oauth.fetch_token(config['issuer'] + '/token', grant_type='authorization_code',
                code=code, code_verifier=verifier(config, state), redirect_uri=store.settings.base + '/auth/sso/callback')
        with httpx.Client(timeout=10, follow_redirects=False) as http:
            response = http.get(config['issuer'] + '/jwks')
            response.raise_for_status()
            if len(response.content) > 65536:
                raise ValueError('Oversized OIDC keys')
            jwks = response.json()
        validate_identity(config, token['id_token'], jwks, bound['nonce'])
        user = conn.execute(text('SELECT id FROM users WHERE email=:email AND active'),
                            {'email': config['hub_owner_email']}).mappings().one_or_none()
        if user is None or not store.memberships(conn, user['id']):
            raise ValueError('SSO owner has no active workspace')
        conn.execute(text('DELETE FROM auth_browser_sessions WHERE id=:id'), {'id': session['id']})
        new_cookie, _ = store.new_session(conn, user['id'], session['pending_authorize'])
        return {'cookie': new_cookie, 'next': session['pending_authorize'] or '/auth/account'}
