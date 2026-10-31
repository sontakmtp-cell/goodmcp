"""A new HTTP request must not trust a credential inherited from another context."""
import asyncio
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest
from mcp.server.auth.provider import AccessToken
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from apps.api.mcp_auth import AccessBoundary, DatabaseVerifier, current_token
from goodmcp.auth_config import AuthSettings

BASE = 'http://127.0.0.1:18080'
TOKEN = 'synthetic-auth-boundary-token-' + 'x' * 32
WORKSPACE = '10000000-0000-4000-8000-000000000001'
USER = '10000000-0000-4000-8000-000000000002'


@pytest.mark.parametrize('still_active', [False, True])
def test_request_revalidates_inherited_token(still_active):
    settings = AuthSettings(BASE, BASE + '/auth', BASE + '/mcp', '127.0.0.1:18080', BASE, False)
    database = MagicMock()
    query = database.engine.connect.return_value.__enter__.return_value.execute
    query.return_value.mappings.return_value.one_or_none.return_value = {
        'client_id': 'synthetic-client', 'scopes': ['hub:read'], 'expires_at': 4102444800,
        'user_id': UUID(USER), 'workspace_id': UUID(WORKSPACE),
        'issuer': settings.issuer, 'resource': settings.resource,
    } if still_active else None
    verifier = DatabaseVerifier(database, settings)

    async def endpoint(request):
        # The SDK's inner check may reuse the credential just validated for this request.
        assert await verifier.verify_token(TOKEN) is request.state.access_token
        return JSONResponse({'verified': True})

    app = Starlette(routes=[Route('/api/v1/me/workspaces', endpoint)])
    app.add_middleware(AccessBoundary, verifier=verifier, settings=settings)

    async def scenario():
        inherited = AccessToken(token=TOKEN, client_id='synthetic-client', scopes=['hub:read'],
            expires_at=4102444800, resource=settings.resource, subject=USER,
            claims={'workspace_id': WORKSPACE, 'issuer': settings.issuer})
        reset = current_token.set(inherited)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
                response = await client.get('/api/v1/me/workspaces', headers={'Authorization': 'Bearer ' + TOKEN})
            assert response.status_code == (200 if still_active else 401)
            assert query.call_count == 1
        finally: current_token.reset(reset)

    asyncio.run(scenario())
