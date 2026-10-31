"""Unauthenticated endpoint evidence for G7; never creates a connector or grant."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
PATHS = ('/', '/mcp', '/.well-known/oauth-protected-resource/mcp',
         '/.well-known/oauth-authorization-server/auth', '/health/ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origins', nargs='+', default=['https://goodmcp.si',
        'https://mcp.goodmcp.si', 'https://auth.goodmcp.si', 'https://admin.goodmcp.si'])
    parser.add_argument('--evidence', type=Path, default=ROOT / 'Docs/reports/evidence/G7/endpoint-probes.json')
    args = parser.parse_args()
    rows = []
    for origin in args.origins:
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            parser.error('Use HTTPS origins without credentials, query or path')
        try:
            dns = sorted({x[4][0] for x in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)})
        except OSError as error:
            dns = {'error_type': type(error).__name__, 'errno': error.errno}
        for path in PATHS:
            row = {'url': origin.rstrip('/') + path, 'dns': dns,
                   'observed_at': datetime.now(timezone.utc).isoformat()}
            if isinstance(dns, dict):
                row['error_type'] = 'DNS resolution failed'
                rows.append(row)
                continue
            try:
                r = httpx.get(row['url'], timeout=15, follow_redirects=False)
                row.update(status=r.status_code, content_type=r.headers.get('content-type'),
                    server=r.headers.get('server'), bytes=len(r.content),
                    response_sha256=hashlib.sha256(r.content).hexdigest())
                if r.headers.get('location'):
                    target = urlsplit(r.headers['location'])
                    row['redirect_without_query'] = target._replace(query='', fragment='').geturl()
                if 'json' in r.headers.get('content-type', ''):
                    # Record only discovery/health/error metadata, never cookies/credentials.
                    data = r.json()
                    row['metadata'] = {k: data[k] for k in ('resource', 'authorization_servers', 'issuer',
                        'authorization_endpoint', 'token_endpoint', 'registration_endpoint',
                        'error', 'error_description', 'resource_metadata') if k in data}
                else:
                    title = re.search(r'<title[^>]*>(.*?)</title>', r.text, re.S | re.I)
                    row['page_title'] = title[1][:160] if title else None
            except (httpx.RequestError, ValueError) as error:
                row['error_type'] = type(error).__name__
            rows.append(row)
    report = {'observed_at': datetime.now(timezone.utc).isoformat(),
        'method': 'Unauthenticated GET, TLS verified, redirects not followed, no cookies retained; local-network probe, not provider-cloud evidence.',
        'records': rows}
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'requests': len(rows), 'evidence': str(args.evidence), 'cloud_acceptance': False}))


if __name__ == '__main__':
    main()
