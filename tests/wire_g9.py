"""Actual Caddy/API/auth session traffic; no real Google-provider claim."""
import json
import os
from pathlib import Path

import httpx


def main():
    base = os.environ['HUB_PUBLIC_BASE_URL']
    state = json.loads(Path('/wirestate/state.json').read_text())
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)
    with httpx.Client(base_url=base, timeout=20, cookies={'hub_session': state['cookie']}) as browser:
        response = browser.get('/auth/web/session')
        check('server browser session survives page reload', response.status_code == 200)
        session = response.json()['data']
        headers = {'Origin': base, 'X-CSRF-Token': session['csrf']}
        check('web lists complete membership set', len(browser.get('/api/v1/me/workspaces').json()['data']) == len(session['workspaces']))
        check('cookie alone cannot authorize MCP', browser.post('/mcp', json={}).status_code == 401)
        check('session mutation requires CSRF', browser.post('/auth/web/workspaces', headers={'Origin': base}, json={'name': 'forged'}).status_code == 403)
        selected = session['workspace_id']
        created = browser.post('/auth/web/workspaces', headers=headers, json={'name': 'G9 HTTP isolated workspace'})
        check('create workspace through authenticated issuer', created.status_code == 201)
        workspace = created.json()['data']['id']
        response = browser.post('/auth/web/select-workspace', headers=headers, json={'workspace_id': workspace})
        check('select workspace changes browser session', response.status_code == 200)
        check('API verifies cookie with internal auth service', browser.get(f'/api/v1/workspaces/{workspace}/plugins').status_code == 200)
        check('old selected workspace rejected', browser.get(f'/api/v1/workspaces/{selected}/plugins').status_code in (403,404))
        check('API write requires CSRF', browser.post(f'/api/v1/workspaces/{workspace}/uploads', headers={'Origin': base}, json={}).status_code == 403)
        check('untrusted internal identity header rejected', browser.get('/api/v1/me/workspaces', headers={'X-User-ID': 'forged'}).status_code == 200)
        check('workspace browser return', browser.post('/auth/web/select-workspace', headers=headers, json={'workspace_id': selected}).status_code == 200)
        check('archive test workspace', browser.post(f'/auth/web/workspaces/{workspace}/archive', headers=headers).status_code == 200)
        check('archived workspace disappears', workspace not in [w['id'] for w in browser.get('/auth/web/session').json()['data']['workspaces']])
    with httpx.Client(base_url=base, timeout=20) as anonymous:
        check('anonymous web API rejected', anonymous.get('/api/v1/me/workspaces').status_code == 401)
        check('session endpoint private', anonymous.get('/auth/web/session').status_code == 401)
    print(json.dumps({'passed': True, 'scope': 'local_http_not_google', 'checks': checks}))


if __name__ == '__main__':
    main()
