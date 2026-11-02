"""Direct Google OIDC. Subject identity, explicit account linking, one-use callbacks."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.jose import JsonWebToken
from sqlalchemy import text

from .cloudflare_sso import sign_state, verify_state, verifier, encode
from .oauth_store import sha


def configuration():
    filename = os.environ.get('HUB_GOOGLE_CONFIG_FILE')
    if not filename or os.environ.get('HUB_GOOGLE_ENABLED', '1') != '1':
        return None
    config = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
    if not config.get('client_id', '').endswith('.apps.googleusercontent.com') or not config.get('client_secret') or len(config.get('state_key', '')) < 43:
        raise ValueError('Incomplete Google configuration')
    return config


def authorization_url(store, config, cookie, *, link=False):
    state = sign_state(config, cookie)
    bound = verify_state(config, cookie, state)
    with store.engine.begin() as conn:
        session = store.session(conn, cookie, lock=True)
        if session is None or (link and not session['user_id']):
            raise ValueError('Authenticated session required for linking')
        conn.execute(text("DELETE FROM auth_google_flows WHERE expires_at<now()"))
        conn.execute(text("""INSERT INTO auth_google_flows(state_hash,session_id,link_user_id,expires_at)
            VALUES(:state,:session,:user,to_timestamp(:expires))"""),
            {'state': sha(state), 'session': session['id'], 'user': session['user_id'] if link else None, 'expires': bound['expires']})
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': config['client_id'], 'redirect_uri': store.settings.base + '/auth/google/callback',
        'response_type': 'code', 'scope': 'openid email profile', 'state': state,
        'nonce': bound['nonce'], 'code_challenge_method': 'S256',
        'code_challenge': encode(hashlib.sha256(verifier(config, state).encode()).digest()),
        'prompt': 'select_account'})


def validate_identity(config, token, jwks, nonce):
    claims = JsonWebToken(['RS256']).decode(token, jwks, claims_options={
        'iss': {'essential': True, 'values': ['https://accounts.google.com', 'accounts.google.com']},
        'aud': {'essential': True, 'value': config['client_id']},
        'exp': {'essential': True}, 'iat': {'essential': True},
        'sub': {'essential': True}, 'nonce': {'essential': True, 'value': nonce},
        'email': {'essential': True}, 'email_verified': {'essential': True, 'value': True}})
    claims.validate(leeway=30)
    if not isinstance(claims['sub'], str) or not 1 <= len(claims['sub']) <= 255:
        raise ValueError('Invalid Google subject')
    if claims.get('email_verified') is not True or not isinstance(claims['email'], str) or len(claims['email']) > 254:
        raise ValueError('Verified Google email required')
    if claims.get('azp') and claims['azp'] != config['client_id']:
        raise ValueError('Invalid authorized party')
    return claims


def provision(conn, claims, *, link_user_id=None, allow_signup=False):
    """The surrounding transaction owns identity, user and personal workspace together."""
    subject, email = claims['sub'], claims['email'].strip().lower()
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {'key': 'google:' + subject})
    identity = conn.execute(text("SELECT user_id FROM user_identities WHERE provider='google' AND subject=:sub"), {'sub': subject}).scalar_one_or_none()
    if link_user_id:
        user = conn.execute(text('SELECT id FROM users WHERE id=:u AND active FOR UPDATE'), {'u': link_user_id}).first()
        if not user or (identity and identity != link_user_id):
            raise ValueError('Google identity already linked or account unavailable')
        existing = conn.execute(text("SELECT subject FROM user_identities WHERE provider='google' AND user_id=:u"), {'u': link_user_id}).scalar_one_or_none()
        if existing and existing != subject:
            raise ValueError('Account already has another Google identity')
        user_id = link_user_id
    elif identity:
        user_id = identity
        if not conn.execute(text('SELECT 1 FROM users WHERE id=:u AND active FOR UPDATE'), {'u': user_id}).first():
            raise ValueError('Account disabled')
    else:
        if not allow_signup:
            raise ValueError('Registration is limited to the verification group')
        user_id = conn.execute(text("INSERT INTO users(email,password_hash,name,email_verified) VALUES(:email,'!',:name,true) RETURNING id"),
            {'email': email, 'name': str(claims.get('name', ''))[:200]}).scalar_one()
        workspace_id = conn.execute(text('INSERT INTO workspaces(name) VALUES(:name) RETURNING id'),
            {'name': (str(claims.get('name') or email.split('@')[0])[:120] + ' — cá nhân')}).scalar_one()
        conn.execute(text("INSERT INTO memberships(workspace_id,user_id,role) VALUES(:ws,:u,'owner')"), {'ws': workspace_id, 'u': user_id})
    if not identity:
        conn.execute(text("INSERT INTO user_identities(user_id,provider,subject,email) VALUES(:u,'google',:sub,:email)"),
                     {'u': user_id, 'sub': subject, 'email': email})
    # A recovery owner may have a legacy email. Linking does not rewrite that address.
    if not link_user_id:
        conn.execute(text("UPDATE users SET email=:email,name=:name,email_verified=true WHERE id=:u AND password_hash='!'"),
                     {'u': user_id, 'email': email, 'name': str(claims.get('name', ''))[:200]})
    return user_id


def finish(store, config, cookie, state, code):
    bound = verify_state(config, cookie, state)
    if not isinstance(code, str) or not 1 <= len(code) <= 4096:
        raise ValueError('Invalid Google callback')
    # Consume before the network call: failures require starting a new login.
    with store.engine.begin() as conn:
        session = store.session(conn, cookie, lock=True)
        if session is None:
            raise ValueError('Missing browser session')
        flow = conn.execute(text("""UPDATE auth_google_flows SET consumed_at=now() WHERE state_hash=:state
            AND session_id=:session AND consumed_at IS NULL AND expires_at>now() RETURNING link_user_id"""),
            {'state': sha(state), 'session': session['id']}).mappings().one_or_none()
        if flow is None:
            raise ValueError('Expired or already consumed callback')
        if flow['link_user_id'] and session['user_id'] != flow['link_user_id']:
            raise ValueError('Link session changed')
        pending, selected = session['pending_authorize'], session['selected_workspace_id']
    with OAuth2Client(config['client_id'], config['client_secret'], token_endpoint_auth_method='client_secret_post',
                      timeout=10, follow_redirects=False) as oauth:
        token = oauth.fetch_token('https://oauth2.googleapis.com/token', grant_type='authorization_code', code=code,
            code_verifier=verifier(config, state), redirect_uri=store.settings.base + '/auth/google/callback')
    with httpx.Client(timeout=10, follow_redirects=False) as http:
        response = http.get('https://www.googleapis.com/oauth2/v3/certs')
        response.raise_for_status()
        if len(response.content) > 65536:
            raise ValueError('Oversized Google key response')
        claims = validate_identity(config, token['id_token'], response.json(), bound['nonce'])
    allow = config.get('signup_enabled') is True or claims['email'].lower() in {e.lower() for e in config.get('testing_emails', [])}
    with store.engine.begin() as conn:
        # Logout/block during Google's response prevents completion/linking.
        session = store.session(conn, cookie, lock=True)
        if not session or (flow['link_user_id'] and session['user_id'] != flow['link_user_id']):
            raise ValueError('Browser session expired')
        user_id = provision(conn, claims, link_user_id=flow['link_user_id'], allow_signup=allow)
        conn.execute(text('DELETE FROM auth_browser_sessions WHERE id=:id'), {'id': session['id']})
        new_cookie, _ = store.new_session(conn, user_id, pending)
        # Verify invitation email only when the current Google login proves the account email.
        account_email = conn.execute(text('SELECT email FROM users WHERE id=:u'), {'u': user_id}).scalar_one()
        conn.execute(text('UPDATE auth_browser_sessions SET email_verified=:verified,selected_workspace_id=:ws WHERE token_hash=:h'),
            {'h': sha(new_cookie), 'verified': account_email.lower() == claims['email'].lower(), 'ws': selected})
    return {'cookie': new_cookie, 'next': pending or '/app'}
