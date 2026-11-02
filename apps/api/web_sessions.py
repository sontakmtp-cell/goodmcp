"""Browser-only session endpoints, hosted on the issuer's private database role."""
import hmac
import os
from pathlib import Path
import secrets
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import text
from starlette.responses import JSONResponse

from goodmcp import google_oidc
from goodmcp.database import Forbidden, NotFound
from goodmcp.oauth_store import sha

COOKIE = 'hub_session'


def csrf_token(cookie):
    return sha(cookie + ':web-csrf')


def internal_key():
    filename = os.environ.get('HUB_WEB_SESSION_KEY_FILE')
    if not filename:
        return None
    value = Path(filename).read_text().strip()
    if len(value) < 43:
        raise RuntimeError('Internal session service key too short')
    return value


def authenticate(request, write=False):
    store = request.app.state.store
    cookie = request.cookies.get(COOKIE)
    if write and (request.headers.get('origin') != store.settings.origin or not cookie or
                  not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf_token(cookie))):
        raise Forbidden('Phiên hoặc mã bảo vệ yêu cầu không hợp lệ')
    with store.engine.begin() as conn:
        session = store.session(conn, cookie)
        if not session or not session['user_id']:
            raise NotFound('authentication_required')
        user = conn.execute(text('SELECT id,email,name,platform_admin,active,email_verified FROM users WHERE id=:u AND active'),
                            {'u': session['user_id']}).mappings().one_or_none()
        if user is None:
            raise NotFound('authentication_required')
        return {**session, 'platform_admin': user['platform_admin'], 'user': dict(user)}


def session_data(store, cookie):
    with store.engine.begin() as conn:
        session = store.session(conn, cookie, lock=True)
        if not session or not session['user_id']:
            return None
        user = conn.execute(text('SELECT id,email,name,platform_admin FROM users WHERE id=:u AND active'),
                            {'u': session['user_id']}).mappings().one_or_none()
        if user is None:
            return None
        memberships = [dict(m) for m in store.memberships(conn, user['id'])]
        selected = session['selected_workspace_id']
        if selected not in {m['workspace_id'] for m in memberships}:
            selected = memberships[0]['workspace_id'] if memberships else None
            conn.execute(text('UPDATE auth_browser_sessions SET selected_workspace_id=:ws WHERE id=:id'), {'ws': selected, 'id': session['id']})
        linked = bool(conn.execute(text("SELECT 1 FROM user_identities WHERE user_id=:u AND provider='google'"), {'u': user['id']}).first())
        return {'user': {**dict(user), 'email_verified': session['email_verified'], 'google_linked': linked},
                'workspace_id': selected, 'workspaces': [{'id': m['workspace_id'], 'name': m['name'], 'role': m['role']} for m in memberships],
                'csrf': csrf_token(cookie), 'google_enabled': google_oidc.configuration() is not None}


def routes():
    router = APIRouter()

    @router.get('/auth/web/config')
    def config():
        return {'data': {'google_enabled': google_oidc.configuration() is not None}}

    @router.get('/auth/web/session')
    def current(request: Request):
        data = session_data(request.app.state.store, request.cookies.get(COOKIE))
        if data is None:
            return JSONResponse({'error': {'code': 'unauthenticated', 'message': 'Đăng nhập để tiếp tục'}}, status_code=401)
        return {'data': data}

    @router.post('/auth/web/select-workspace')
    async def select(request: Request):
        session = authenticate(request, write=True)
        body = await request.json()
        workspace = UUID(str(body.get('workspace_id')))
        store = request.app.state.store
        with store.engine.begin() as conn:
            if workspace not in {m['workspace_id'] for m in store.memberships(conn, session['user_id'])}:
                raise NotFound('Workspace not found')
            conn.execute(text('UPDATE auth_browser_sessions SET selected_workspace_id=:ws WHERE id=:id'), {'ws': workspace, 'id': session['id']})
        return {'data': {'workspace_id': workspace}}

    @router.post('/auth/web/logout')
    async def logout(request: Request):
        session = authenticate(request, write=True)
        body = await request.json()
        store = request.app.state.store
        with store.engine.begin() as conn:
            if body.get('all_devices') is True:
                conn.execute(text('DELETE FROM auth_browser_sessions WHERE user_id=:u'), {'u': session['user_id']})
            else:
                conn.execute(text('DELETE FROM auth_browser_sessions WHERE id=:id'), {'id': session['id']})
        response = JSONResponse({'data': {'logged_out': True}})
        response.delete_cookie(COOKIE, path='/', secure=store.settings.secure_cookie, httponly=True, samesite='lax')
        response.delete_cookie(COOKIE, path='/auth', secure=store.settings.secure_cookie, httponly=True, samesite='lax')
        return response

    @router.post('/auth/web/google/link')
    def link(request: Request):
        authenticate(request, write=True)
        config = google_oidc.configuration()
        if not config:
            raise Forbidden('Google chưa được cấu hình')
        return {'data': {'url': google_oidc.authorization_url(request.app.state.store, config, request.cookies[COOKIE], link=True)}}

    @router.post('/internal/web-session')
    async def internal(request: Request):
        key = internal_key()
        if not key or not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + key):
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        body = await request.json()
        cookie = body.get('cookie')
        if not isinstance(cookie, str) or not 30 <= len(cookie) <= 128:
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        if body.get('method') not in ('GET', 'HEAD', 'OPTIONS') and not hmac.compare_digest(str(body.get('csrf', '')), csrf_token(cookie)):
            return JSONResponse({'error': 'csrf'}, status_code=403)
        data = session_data(request.app.state.store, cookie)
        if data is None:
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        return {'data': data}

    return router
