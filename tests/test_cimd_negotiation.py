import pytest
from goodmcp.auth_config import SCOPES
from goodmcp.oauth_clients import validate_metadata, validate_cimd_metadata, redirect_csp_origin


def metadata(**changes):
    return {'client_id': 'https://client.example/oauth/client.json', 'client_name': 'Generic CIMD client',
            'redirect_uris': ['https://client.example/callback'], 'token_endpoint_auth_method': 'private_key_jwt',
            'token_endpoint_auth_methods_supported': ['none', 'private_key_jwt'], **changes}


def test_cimd_plural_capability_negotiates_only_supported_public_pkce_method():
    result = validate_cimd_metadata(metadata(), allow_loopback=False)
    assert result['allowed_scopes'] == sorted(SCOPES)
    assert result['redirect_uris'] == ['https://client.example/callback']


def test_explicit_cimd_scope_is_not_expanded():
    assert validate_cimd_metadata(metadata(scope='hub:read'), allow_loopback=False)['allowed_scopes'] == ['hub:read']


@pytest.mark.parametrize('methods', [['private_key_jwt'], [], 'none', [None, 'none']])
def test_no_intersection_or_invalid_methods_are_rejected(methods):
    with pytest.raises(ValueError):
        validate_cimd_metadata(metadata(token_endpoint_auth_methods_supported=methods), allow_loopback=False)


def test_legacy_confidential_client_and_dcr_cannot_silently_switch_method():
    data = metadata()
    with pytest.raises(ValueError):
        validate_metadata(data, allow_loopback=False)
    del data['token_endpoint_auth_methods_supported']
    with pytest.raises(ValueError):
        validate_cimd_metadata(data, allow_loopback=False)
    assert validate_metadata({'redirect_uris': ['https://client.example/callback']}, allow_loopback=False)['allowed_scopes'] == ['hub:read']


@pytest.mark.parametrize('uri,origin', [('https://client.example/callback?state=private', 'https://client.example'),
    ('http://127.0.0.1:8766/callback', 'http://127.0.0.1:8766'),
    ('http://[::1]:8766/callback', 'http://[::1]:8766')])
def test_callback_csp_origin_does_not_disclose_query_or_widen_to_any_host(uri, origin):
    assert redirect_csp_origin(uri) == origin


@pytest.mark.parametrize('uri', ['javascript:alert(1)', 'https://client.example;script-src/cb',
    'https://client.example/\ncallback', 'https://user:password@client.example/callback'])
def test_callback_csp_source_injection_rejected(uri):
    with pytest.raises(ValueError):
        redirect_csp_origin(uri)
