"""G7 supporting evidence: real local OAuth/HTTP/MCP, never a cloud-host pass.

Uses the existing owner and enabled plugins. Retains one explicitly labelled test
project and its immutable outputs; revokes both temporary grants in finally.
Does not configure hosts, deploy, downgrade MCP or invoke a model API.
"""
import argparse
import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
from pathlib import Path
import re
import secrets
import subprocess
import shutil
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:18080'
PROTOCOL = '2026-07-28'
SCOPES = 'hub:read hub:write tools:run projects:read projects:write'


async def run(out):
    report = {'status': 'in_progress', 'classification': 'protocol_only',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'endpoint': BASE + '/mcp', 'protocol': PROTOCOL,
              'host': 'official Python SDK; local HTTP harness',
              'requested_model': None, 'reported_model': 'unknown',
              'model_api_calls': 0, 'checks': [], 'calls': [], 'grants': [],
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
                  if shutil.which('git') and (ROOT / '.git').is_dir() else 'unknown; see deployment image/source manifest',
              'versions': {n: importlib.metadata.version(n) for n in ('mcp', 'httpx', 'httpx2')}}
    grants = []

    def check(name, condition, **observed):
        report['checks'].append({'name': name, 'passed': bool(condition), **observed})
        if not condition:
            raise AssertionError(name)

    def csrf(response):
        check('OAuth form responds with HTML', response.status_code == 200)
        match = re.search(r'name="csrf"[^>]*value="([^"\s]+)"', response.text)
        check('OAuth CSRF present', match is not None)
        return html.unescape(match[1])

    def login(label):
        redirect = 'http://127.0.0.1:8766/callback'
        with httpx.Client(base_url=BASE, timeout=30) as browser:
            registration = browser.post('/auth/register', json={
                'client_name': 'G7 local protocol ' + label, 'redirect_uris': [redirect], 'scope': SCOPES})
            check('OAuth DCR ' + label, registration.status_code == 201)
            client_id = registration.json()['client_id']
            page = browser.get('/auth/login')
            password = (ROOT / '.local/secrets/owner_password').read_text().strip()
            signed = browser.post('/auth/login', data={'csrf': csrf(page), 'email': 'owner@local.invalid', 'password': password})
            check('Owner login ' + label, signed.status_code == 303)
            verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            page = browser.get('/auth/authorize', params={'response_type': 'code', 'client_id': client_id,
                'redirect_uri': redirect, 'resource': BASE + '/mcp', 'scope': SCOPES,
                'state': state, 'code_challenge_method': 'S256', 'code_challenge': challenge})
            options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', page.text)
            check('Owner workspace available ' + label, bool(options))
            workspace = next(v for v, name in options if 'G2 revoked fixture' not in name)
            consent = browser.post('/auth/authorize', data={'csrf': csrf(page), 'workspace_id': workspace, 'consent': 'allow'})
            check('Explicit consent ' + label, consent.status_code == 302)
            fields = parse_qs(urlsplit(consent.headers['location']).query)
            check('OAuth state and issuer binding ' + label, fields.get('state') == [state] and fields.get('iss') == [BASE + '/auth'])
            exchanged = browser.post('/auth/token', data={'grant_type': 'authorization_code',
                'client_id': client_id, 'redirect_uri': redirect, 'resource': BASE + '/mcp',
                'code': fields['code'][0], 'code_verifier': verifier})
            check('PKCE token exchange ' + label, exchanged.status_code == 200)
            credential = {**exchanged.json(), 'client_id': client_id, 'workspace': workspace, 'label': label}
            grants.append(credential)
            return credential

    @asynccontextmanager
    async def connect(credential):
        async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + credential['access_token']}) as http:
            async with Client(streamable_http_client(BASE + '/mcp', http_client=http), mode=PROTOCOL) as client:
                check('SDK strict modern protocol ' + credential['label'], client.protocol_version == PROTOCOL,
                      observed_protocol=client.protocol_version)
                yield client

    async def call(client, name, arguments):
        started = time.monotonic()
        result = await client.call_tool(name, arguments)
        report['calls'].append({'tool': name, 'argument_keys': sorted(arguments),
            'is_error': bool(result.is_error), 'elapsed_s': round(time.monotonic() - started, 4)})
        check('MCP ' + name, not result.is_error)
        return result.structured_content

    try:
        with httpx.Client(base_url=BASE, timeout=20) as http:
            ready = http.get('/health/ready')
            check('Persistent stack ready', ready.status_code == 200 and ready.json()['data']['status'] == 'ready')
            report['readiness'] = ready.json()['data']
            resource = http.get('/.well-known/oauth-protected-resource/mcp').json()
            check('Local protected resource discovery', resource['resource'] == BASE + '/mcp')
            issuer = http.get('/.well-known/oauth-authorization-server/auth').json()
            check('Local issuer and S256 discovery', issuer['issuer'] == BASE + '/auth' and 'S256' in issuer['code_challenge_methods_supported'])
        first = login('session-A')
        async with connect(first) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            required = {'hub_list_plugins', 'hub_open_plugin', 'hub_get_skill', 'hub_search',
                'hub_read_document', 'finance_cit_estimate', 'hub_get_job', 'hub_open_project',
                'hub_save_artifact', 'hub_read_project', 'hub_read_project_file'}
            check('Required tools discoverable', required <= names)
            report['tool_names'] = sorted(names)
            listing = await call(client, 'hub_list_plugins', {'limit': 100})
            enabled = [p for p in listing['items'] if p['enabled']]
            report['enabled_plugins'] = enabled
            finance = None
            skill = None
            for plugin in enabled:
                opened = await call(client, 'hub_open_plugin', {'installation_id': plugin['installation_id']})
                preview = opened['preview']
                if 'finance' in json.dumps(preview).lower():
                    finance = plugin
                for role in preview.get('skills', []):
                    name = role if isinstance(role, str) else role.get('name')
                    if name and skill is None:
                        skill = await call(client, 'hub_get_skill', {'installation_id': plugin['installation_id'], 'name': name})
            check('Actual plugin skill read', bool(skill and skill['body']))
            report['skill'] = {k: skill[k] for k in ('name', 'version_id', 'source_trust')}
            check('Finance plugin enabled', finance is not None)
            iid = finance['installation_id']
            docs = await call(client, 'hub_list_documents', {'installation_id': iid, 'limit': 100})
            check('Source documents listed', bool(docs['items']))
            matched = await call(client, 'hub_search', {'installation_id': iid, 'keywords': ['tax'], 'limit': 2})
            check('Literal search finds real source', bool(matched['items']))
            doc = await call(client, 'hub_read_document', {'installation_id': iid,
                'resource_id': matched['items'][0]['resource_id'], 'length': 1024})
            check('Matched plain text read with source digest', bool(doc['content']) and len(doc['source_sha256']) == 64)
            report['document'] = {k: doc[k] for k in ('resource_id', 'logical_path', 'source_sha256', 'offset', 'next_offset')}
            args = {'installation_id': iid, 'arguments': {'revenue': 1000, 'cost': 600, 'rate': 20},
                    'idempotency_key': 'g7-' + uuid4().hex}
            job = (await call(client, 'finance_cit_estimate', args))['job']
            retried = (await call(client, 'finance_cit_estimate', args))['job']
            check('Same invocation reuses one job', retried['id'] == job['id'])
            deadline = time.monotonic() + 90
            states = [job['state']]
            while job['state'] in ('queued', 'running') and time.monotonic() < deadline:
                await asyncio.sleep(.2)
                job = (await call(client, 'hub_get_job', {'job_id': job['id']}))['job']
                states.append(job['state'])
            report['job'] = job
            report['observed_job_states'] = states
            check('Actual Python job succeeds', job['state'] == 'succeeded')
            release = json.loads((ROOT / '.local/g4/active/release.json').read_text())
            result = job['result']
            check('Approved original Python provenance', result['provenance']['original_python'] is True
                  and result['provenance']['image_digest'] == release['image_digest']
                  and result['provenance']['release_digest'] == release['release_digest'])
            check('Python result matches 80 VND', result['data']['cit_with_incentive_VND'] == 80)
            project = (await call(client, 'hub_open_project', {'payload': {'installation_id': iid,
                'name': 'G7 LOCAL PROTOCOL acceptance ' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                'idempotency_key': uuid4().hex}}))['data']
            report['project_id'] = project['id']
            note = 'G7 local protocol test, not cloud host acceptance.\nPython CIT: 80 VND.\nJob: ' + job['id'] + '\n'
            payload = {'logical_path': 'opc-doc/outputs/g7-protocol.md', 'content': note,
                       'expected_revision': 0, 'idempotency_key': uuid4().hex}
            saved = (await call(client, 'hub_save_artifact', {'project_id': project['id'], 'payload': payload}))['data']
            file_id = saved['file']['id']
            original = (await call(client, 'hub_read_project', {'project_id': project['id']}))['data']
            check('Saved output is draft and does not fabricate stage completion',
                  any(f['id'] == file_id and f['status'] == 'draft' for f in original['files']))
        second = login('session-B')
        check('Independent OAuth grant accesses same workspace', second['workspace'] == first['workspace'] and second['access_token'] != first['access_token'])
        async with connect(second) as client:
            projects = (await call(client, 'hub_list_projects', {'limit': 100}))['data']
            check('New session discovers retained project', any(p['id'] == project['id'] for p in projects['items']))
            reopened = (await call(client, 'hub_read_project', {'project_id': project['id']}))['data']
            check('New session preserves pin revision and resume stage',
                  all(reopened[k] == original[k] for k in ('plugin_version_id', 'revision', 'resume_stage')))
            readback = (await call(client, 'hub_read_project_file', {'project_id': project['id'], 'file_id': file_id}))['data']
            check('Readback text and digest identical', readback['content'] == note and readback['sha256'] == hashlib.sha256(note.encode()).hexdigest())
            report['persisted_file'] = {'id': file_id, 'sha256': readback['sha256'], 'revision': reopened['revision'],
                'plugin_version_id': reopened['plugin_version_id'], 'resume_stage': reopened['resume_stage']}
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        def types_only(exc):
            return [item for child in getattr(exc, 'exceptions', []) for item in types_only(child)] or [
                {'type': type(exc).__name__, 'detail': str(exc) if isinstance(exc, (KeyError, AttributeError, TypeError)) else 'redacted'}]
        # Do not serialize HTTP requests, exception groups or token-bearing URLs.
        report['failure'] = {'type': type(error).__name__, 'check': next((x['name'] for x in reversed(report['checks']) if not x['passed']), 'unexpected harness exception; inspect locally')}
        report['failure']['leaves'] = types_only(error)
    finally:
        with httpx.Client(base_url=BASE, timeout=20) as http:
            for credential in grants:
                try:
                    revoked = http.post('/auth/revoke', data={'client_id': credential['client_id'], 'token': credential['access_token']})
                    headers = {'Authorization': 'Bearer ' + credential['access_token'], 'Cache-Control': 'no-store'}
                    rest = http.get('/api/v1/me/workspaces?g7=' + uuid4().hex, headers=headers)
                    rpc = http.post('/mcp', headers={**headers, 'MCP-Protocol-Version': PROTOCOL,
                        'Accept': 'application/json, text/event-stream', 'Mcp-Method': 'tools/list'},
                        json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {'_meta': {
                            'io.modelcontextprotocol/protocolVersion': PROTOCOL,
                            'io.modelcontextprotocol/clientCapabilities': {},
                            'io.modelcontextprotocol/clientInfo': {'name': 'g7-revoked-probe', 'version': '1'}}}})
                    clean = revoked.status_code == 200 and rest.status_code == rpc.status_code == 401
                    report['grants'].append({'label': credential['label'], 'revoke_http': revoked.status_code,
                        'rest_after_revoke': rest.status_code, 'mcp_after_revoke': rpc.status_code, 'passed': clean})
                    if not clean:
                        report['status'] = 'failed'
                except Exception as error:
                    report['grants'].append({'label': credential['label'], 'passed': False, 'error_type': type(error).__name__})
                    report['status'] = 'failed'
        report['ended_at'] = datetime.now(timezone.utc).isoformat()
        report['fixture_retained'] = 'One labelled project/output if created; existing installations unchanged; test grants revoked as recorded.'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf8')
        print(json.dumps({'status': report['status'], 'classification': 'protocol_only',
            'checks': len(report['checks']), 'failure': report.get('failure'), 'evidence': str(out)}))
    return report['status'] == 'passed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true', required=True, help='Explicitly exercise existing local stack')
    parser.add_argument('--base-url', default=BASE, help='Loopback only; also used for private restore verification')
    parser.add_argument('--evidence', type=Path, default=ROOT / 'Docs/reports/evidence/G7/local-protocol.json')
    args = parser.parse_args()
    if urlsplit(args.base_url).scheme != 'http' or urlsplit(args.base_url).hostname not in ('127.0.0.1', 'localhost'):
        parser.error('This owner-password harness accepts HTTP loopback only, never a public endpoint')
    BASE = args.base_url.rstrip('/')
    raise SystemExit(0 if asyncio.run(run(args.evidence)) else 1)
