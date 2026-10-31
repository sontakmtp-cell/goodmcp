"""G6 local HTTP acceptance through the frontend dev proxy; no production or LLM.

Runs against the existing local stack. Creates an explicitly labelled private
test plugin/project, disables its installation afterward, and revokes its grant.
--browser-authorize finishes a browser-started PKCE request using the local owner
test harness; only the one-time callback is written to ignored work/, never tokens.
"""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'http://127.0.0.1:4173'
ISSUER = 'http://127.0.0.1:18080/auth'
SCOPES = 'hub:read hub:write tools:run projects:read projects:write'


def csrf(page):
    assert page.status_code == 200, 'Expected login or consent page'
    match = re.search(r'name="csrf"[^>]*value="([^"\s]+)"', page.text)
    assert match, 'Missing CSRF'
    return html.unescape(match[1])


def login(browser):
    page = browser.get('/auth/login')
    password = (ROOT / '.local/secrets/owner_password').read_text().strip()
    result = browser.post('/auth/login', data={'csrf': csrf(page), 'email': 'owner@local.invalid', 'password': password})
    assert result.status_code == 303, 'Local owner login failed'


def authorize(browser, params):
    page = browser.get('/auth/authorize', params=params)
    options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', page.text)
    ws = next(v for v, label in options if 'G2 revoked fixture' not in label)
    result = browser.post('/auth/authorize', data={'csrf': csrf(page), 'workspace_id': ws, 'consent': 'allow'})
    assert result.status_code == 302, 'Local consent failed'
    location = result.headers['location']
    fields = parse_qs(urlsplit(location).query)
    assert fields.get('state') == [params['state']] and fields.get('iss') == [ISSUER]
    return location, fields['code'][0], ws


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-authorize', type=Path)
    parser.add_argument('--evidence-dir', type=Path, default=ROOT / 'Docs/reports/assets/g6')
    args = parser.parse_args()
    with httpx.Client(base_url=ORIGIN, timeout=90) as browser:
        login(browser)
        if args.browser_authorize:
            url = args.browser_authorize.read_text().strip()
            parsed = urlsplit(url)
            assert parsed.scheme == 'http' and parsed.netloc == '127.0.0.1:4173' and parsed.path == '/auth/authorize'
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            assert params['redirect_uri'] == ORIGIN + '/oauth/callback'
            callback, _, _ = authorize(browser, params)
            (ROOT / 'work/g6-callback.txt').write_text(callback)
            print('Browser-started local PKCE callback ready; no tokens saved.')
            return
        client = browser.post('/auth/register', json={'client_name': 'G6 local API acceptance', 'redirect_uris': [ORIGIN + '/oauth/callback'], 'scope': SCOPES})
        assert client.status_code == 201, 'DCR failed'
        client_id = client.json()['client_id']
        verifier = secrets.token_urlsafe(32)
        import base64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        _, code, ws = authorize(browser, {'response_type': 'code', 'client_id': client_id, 'redirect_uri': ORIGIN + '/oauth/callback', 'resource': ISSUER.removesuffix('/auth') + '/mcp', 'scope': SCOPES, 'state': secrets.token_urlsafe(24), 'code_challenge_method': 'S256', 'code_challenge': challenge})
        result = browser.post('/auth/token', data={'grant_type': 'authorization_code', 'client_id': client_id, 'code': code, 'code_verifier': verifier, 'redirect_uri': ORIGIN + '/oauth/callback', 'resource': ISSUER.removesuffix('/auth') + '/mcp'})
        assert result.status_code == 200
        token = result.json()['access_token']
        headers = {'Authorization': 'Bearer ' + token}
        prefix = '/api/v1/workspaces/' + ws
        checks = []
        installation = None

        def check(name, condition):
            checks.append({'name': name, 'passed': bool(condition)})
            assert condition, name

        def request(method, path, **kwargs):
            return browser.request(method, prefix + path, headers={**headers, **kwargs.pop('headers', {})}, **kwargs)

        def data(method, path, **kwargs):
            r = request(method, path, **kwargs)
            assert r.is_success, f'{method} {path}: HTTP {r.status_code}'
            return r.json()['data']

        def wait_upload(uid):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                u = data('GET', '/uploads/' + uid)
                if u['state'] not in ('queued', 'scanning'): return u
                time.sleep(.15)
            raise AssertionError('Import worker timed out')

        def mcp_workspace():
            return browser.post(ISSUER.removesuffix('/auth') + '/mcp', headers={**headers,
                'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2026-07-28',
                'Mcp-Method': 'tools/call', 'Mcp-Name': 'hub_get_workspace'}, json={
                    'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call', 'params': {
                        'name': 'hub_get_workspace', 'arguments': {'workspace_id': ws}, '_meta': {
                            'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                            'io.modelcontextprotocol/clientCapabilities': {},
                            'io.modelcontextprotocol/clientInfo': {'name': 'g6-local-regression', 'version': '1'}}}})

        try:
            check('frontend proxy health uses real backend', browser.get('/health/ready').json()['data']['status'] == 'ready')
            check('unauthenticated REST remains protected', browser.get(prefix + '/plugins').status_code == 401)
            me = browser.get('/api/v1/me/workspaces', headers=headers).json()['data'][0]
            check('workspace and admin role come from verified identity', me['workspace_id'] == ws and me['role'] == 'owner')
            rpc = mcp_workspace()
            check('MCP inner verification accepts a freshly validated request', rpc.status_code == 200 and 'result' in rpc.json() and ws in rpc.text)
            raw = io.BytesIO()
            name = 'g6-ui-acceptance-' + uuid4().hex[:8]
            with zipfile.ZipFile(raw, 'w') as z:
                z.writestr('plugin.json', json.dumps({'name': name, 'version': '1.0.0', 'license': 'MIT'}))
                z.writestr('skills/hello/SKILL.md', '---\nname: hello\ndescription: G6 synthetic UI test, not customer data.\n---\nG6 acceptance document.\n')
                z.writestr('fixtures/padding.bin', secrets.token_bytes(8 * 1024 * 1024))
            payload = raw.getvalue()
            digest = hashlib.sha256(payload).hexdigest()
            body = {'bytes': len(payload), 'sha256': digest, 'idempotency_key': uuid4().hex}
            u = data('POST', '/uploads', json=body)
            check('upload creation is idempotent', data('POST', '/uploads', json=body)['id'] == u['id'])
            uid = u['id']
            first = payload[:u['part_size']]
            data('PUT', f'/uploads/{uid}/parts/0', content=first, headers={'X-Content-SHA256': hashlib.sha256(first).hexdigest()})
            status = data('GET', '/uploads/' + uid)
            check('resume status identifies accepted part without completing', status['received_parts'] == [0] and status['state'] == 'uploading' and status['expected_parts'] == 2)
            check('missing-part complete rejects without pretending success', request('POST', f'/uploads/{uid}/complete').status_code == 409)
            last = payload[u['part_size']:]
            data('PUT', f'/uploads/{uid}/parts/1', content=last, headers={'X-Content-SHA256': hashlib.sha256(last).hexdigest()})
            data('POST', f'/uploads/{uid}/complete')
            ready = wait_upload(uid)
            check('real import worker publishes source-only preview', ready['state'] == 'ready' and ready['preview']['runtime'] == 'source_only_no_execution')
            installation = data('PUT', '/installation', json={'version_id': ready['plugin_version_id'], 'enabled': True, 'expected_revision': 0})
            iid = installation['id']
            page = data('GET', '/plugins')
            check('private catalog includes installed synthetic plugin', any(p['installation_id'] == iid for p in page['items']))
            versions = data('GET', f'/installations/{iid}/versions')['items']
            check('version detail is immutable and source export matches hash', len(versions) == 1 and hashlib.sha256(request('GET', '/versions/' + ready['plugin_version_id'] + '/export').content).hexdigest() == digest)
            check('stale installation revision is rejected', request('PUT', '/installation', json={'version_id': ready['plugin_version_id'], 'enabled': False, 'expected_revision': 0}).status_code == 409)
            docs = data('GET', f'/installations/{iid}/documents')['items']
            match = data('POST', f'/installations/{iid}/documents/search', json={'keywords': ['acceptance'], 'match': 'all'})
            text = data('GET', f'/installations/{iid}/documents/' + next(d['resource_id'] for d in docs if d['logical_path'].endswith('SKILL.md')))
            check('document list search and plain text read use real source', len(match['items']) >= 1 and 'G6 acceptance' in text['content'])
            project = data('POST', '/projects', json={'name': 'G6 synthetic UI acceptance', 'installation_id': iid, 'idempotency_key': uuid4().hex})
            pid = project['id']
            saved = data('POST', f'/projects/{pid}/artifacts', json={'logical_path': 'opc-doc/outputs/g6-note.md', 'content': 'Synthetic G6 acceptance output.', 'expected_revision': 0, 'idempotency_key': uuid4().hex})
            read = data('GET', f'/projects/{pid}')
            file = data('GET', f'/projects/{pid}/files/' + saved['file']['id'])
            check('project pin revision draft and text read persist', read['revision'] == 1 and read['plugin_version_id'] == ready['plugin_version_id'] and file['content'] == 'Synthetic G6 acceptance output.' and read['files'][0]['status'] == 'draft')
            check('stale project save is rejected', request('POST', f'/projects/{pid}/artifacts', json={'logical_path': 'opc-doc/outputs/other.md', 'content': 'stale', 'expected_revision': 0, 'idempotency_key': uuid4().hex}).status_code == 409)
            found_runtime = False
            for p in page['items']:
                if not p['enabled']: continue
                bindings = data('GET', f'/installations/{p["installation_id"]}/bindings')
                binding = next((b for b in bindings if b['mcp_name'] == 'finance_cit_estimate'), None)
                if binding:
                    found_runtime = True
                    check('Python form schema comes from reviewed binding', 'revenue' in binding['input_schema']['properties'])
                    invoke = {'binding_id': binding['id'], 'arguments': {'revenue': 1000, 'cost': 600, 'rate': 20}, 'idempotency_key': uuid4().hex}
                    job = data('POST', '/invocations', json=invoke)
                    check('tool submission retries reuse one job', data('POST', '/invocations', json=invoke)['id'] == job['id'])
                    deadline = time.monotonic() + 60
                    while job['state'] in ('queued', 'running') and time.monotonic() < deadline:
                        time.sleep(.2); job = data('GET', '/jobs/' + job['id'])
                    checks.append({'name': 'approved Python runner returns durable successful result', 'passed': job['state'] == 'succeeded' and 'result' in job, 'observed_state': job['state'], 'error_code': job.get('error', {}).get('code') if job.get('error') else None})
                    cancelled = data('POST', '/invocations', json={**invoke, 'idempotency_key': uuid4().hex})
                    cancelled = data('POST', '/jobs/' + cancelled['id'] + '/cancel')
                    check('job cancel reflects real terminal or pending stop', cancelled['state'] in ('succeeded', 'cancelled') or cancelled.get('cancel_requested'))
                    break
            check('existing approved local Finance runtime was exercised', found_runtime)
            for endpoint in ('/users', '/connections', '/logs', '/backup', '/metrics'):
                check('unavailable API remains explicit: ' + endpoint, request('GET', endpoint).status_code == 404)
        finally:
            if installation:
                data('PUT', '/installation', json={'version_id': installation['plugin_version_id'], 'enabled': False, 'expected_revision': installation['revision']})
            revoked = browser.post('/auth/revoke', data={'client_id': client_id, 'token': token})
            # Match the UI's explicit revalidation and do not reuse an earlier GET URL.
            after = browser.get('/api/v1/me/workspaces?revoke_check=' + uuid4().hex, headers={**headers, 'Cache-Control': 'no-store'})
            revoked_access_status = after.status_code
            checks.append({'name': 'revoke invalidates the actual web-shaped grant', 'passed': revoked.status_code == 200 and revoked_access_status == 401, 'revoke_status': revoked.status_code, 'access_after_revoke': revoked_access_status})
            revoked_rpc = mcp_workspace()
            checks.append({'name': 'revoked grant is rejected by the real MCP boundary', 'passed': revoked_rpc.status_code == 401, 'status': revoked_rpc.status_code})
            report = {'passed': all(c['passed'] for c in checks), 'scope': 'real local HTTP via Vite proxy and real MCP; synthetic labelled private fixture; no production or model API', 'checks': checks, 'fixture_retained_disabled': bool(installation)}
            out = args.evidence_dir / 'api-local.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            assert all(c['passed'] for c in checks), json.dumps([c for c in checks if not c['passed']])
            print(json.dumps({'passed': sum(c['passed'] for c in checks), 'total': len(checks), 'report': str(out)}, ensure_ascii=False))


if __name__ == '__main__': main()
