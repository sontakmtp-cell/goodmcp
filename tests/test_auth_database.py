import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@pytest.mark.parametrize("table", ["oauth_clients", "oauth_codes", "auth_browser_sessions", "auth_login_limits"])
def test_runtime_cannot_read_issuer_private_tables(db, table):
    with pytest.raises(DBAPIError) as error:
        with db.engine.connect() as conn: conn.execute(text(f"SELECT * FROM {table}"))
    assert error.value.orig.sqlstate == "42501"


def test_runtime_cannot_mint_tokens_or_edit_grants(db):
    with db.engine.connect() as conn:
        for name in ("tokens", "oauth_grants"):
            assert not conn.execute(text("SELECT has_table_privilege(current_user,:name,'INSERT')"), {"name": name}).scalar_one()
            assert not conn.execute(text("SELECT has_table_privilege(current_user,:name,'UPDATE')"), {"name": name}).scalar_one()
        assert conn.execute(text("SELECT count(*) FROM hub_access_identity(:hash,:iss,:aud)"),
                            {"hash": "a"*64, "iss": "https://wrong.invalid/auth", "aud": "https://wrong.invalid/mcp"}).scalar_one() == 0
        f = conn.execute(text("SELECT prosecdef,proconfig FROM pg_proc WHERE proname='hub_access_identity'")).one()
        assert f[0] and f[1] == ["search_path=pg_catalog, public"]
