import time
from urllib.parse import parse_qs, urlsplit

from authlib.jose import JsonWebKey, JsonWebToken
import pytest

from goodmcp.cloudflare_sso import sign_state, verify_state, authorization_url, validate_identity


CONFIG = {'issuer': 'https://team.cloudflareaccess.com/cdn-cgi/access/sso/oidc/test',
          'client_id': 'test-client', 'allowed_email': 'owner@example.invalid', 'state_key': 'x' * 48}


def test_state_expires_cookie_bound_and_tamper_rejected():
    state = sign_state(CONFIG, 'anonymous-browser-cookie', timestamp=1000)
    assert verify_state(CONFIG, 'anonymous-browser-cookie', state, timestamp=1001)['expires'] == 1300
    for cookie, value, timestamp in [('different-cookie', state, 1001),
                                    ('anonymous-browser-cookie', state + 'x', 1001),
                                    ('anonymous-browser-cookie', state, 1300),
                                    ('anonymous-browser-cookie', state, 999)]:
        with pytest.raises(ValueError):
            verify_state(CONFIG, cookie, value, timestamp=timestamp)


def test_authorization_uses_pkce_nonce_fixed_callback():
    url = authorization_url(CONFIG, 'browser-cookie', 'https://hub.example/auth/sso/callback')
    p = urlsplit(url)
    args = parse_qs(p.query)
    assert p.netloc == 'team.cloudflareaccess.com'
    assert args['code_challenge_method'] == ['S256'] and len(args['code_challenge'][0]) == 43
    assert args['nonce'] and args['state'] and args['redirect_uri'] == ['https://hub.example/auth/sso/callback']


@pytest.mark.parametrize('change', [None, {'iss': 'https://attacker.example'}, {'aud': 'other-client'},
    {'nonce': 'other-nonce'}, {'email': 'other@example.invalid'}, {'email_verified': False},
    {'exp': 1}, {'sub': None}])
def test_real_signed_id_token_claims(change):
    key = JsonWebKey.generate_key('RSA', 2048, is_private=True)
    now = int(time.time())
    claims = {'iss': CONFIG['issuer'], 'aud': CONFIG['client_id'], 'iat': now, 'exp': now + 120,
              'nonce': 'expected-nonce', 'email': CONFIG['allowed_email'], 'sub': 'owner-id'}
    claims.update(change or {})
    token = JsonWebToken(['RS256']).encode({'alg': 'RS256'}, claims, key)
    if change is None:
        assert validate_identity(CONFIG, token, key.as_dict(is_private=False), 'expected-nonce')['sub'] == 'owner-id'
    else:
        with pytest.raises(Exception):
            validate_identity(CONFIG, token, key.as_dict(is_private=False), 'expected-nonce')
