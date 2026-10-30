"""Durable OAuth/browser credentials and narrow resource-server token lookup."""
from alembic import op
import sqlalchemy as sa

revision = "0002_g2"
down_revision = "0001_g1"


def upgrade():
    statements = [
        "GRANT USAGE ON SCHEMA public TO hub_auth",
        """CREATE TABLE oauth_clients (
            client_id text PRIMARY KEY, name text NOT NULL, redirect_uris jsonb NOT NULL,
            allowed_scopes jsonb NOT NULL, source text NOT NULL CHECK(source IN ('operator','dcr','cimd')),
            active boolean NOT NULL DEFAULT true, metadata_expires_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE auth_browser_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), token_hash char(64) UNIQUE NOT NULL CHECK(token_hash ~ '^[0-9a-f]{64}$'),
            user_id uuid REFERENCES users(id), csrf_hash char(64) NOT NULL,
            pending_authorize text, expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE auth_login_limits (
            bucket char(64) PRIMARY KEY, attempts integer NOT NULL CHECK(attempts>0),
            expires_at timestamptz NOT NULL)""",
        "ALTER TABLE oauth_grants ADD COLUMN issuer text NOT NULL DEFAULT '', ADD COLUMN resource text NOT NULL DEFAULT ''",
        """CREATE TABLE oauth_codes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id),
            grant_id uuid NOT NULL, code_hash char(64) NOT NULL UNIQUE CHECK(code_hash ~ '^[0-9a-f]{64}$'),
            redirect_uri text NOT NULL, code_challenge text NOT NULL, code_challenge_method text NOT NULL CHECK(code_challenge_method='S256'),
            expires_at timestamptz NOT NULL, consumed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workspace_id,id),
            FOREIGN KEY(workspace_id,grant_id) REFERENCES oauth_grants(workspace_id,id))""",
        """ALTER TABLE tokens ADD COLUMN kind text NOT NULL DEFAULT 'access' CHECK(kind IN ('access','refresh')),
            ADD COLUMN consumed_at timestamptz, ADD COLUMN issuer text NOT NULL DEFAULT '',
            ADD COLUMN resource text NOT NULL DEFAULT '', ADD COLUMN scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN parent_token_id uuid,
            ADD CONSTRAINT fk_token_parent FOREIGN KEY(workspace_id,parent_token_id) REFERENCES tokens(workspace_id,id),
            ADD CONSTRAINT token_hash_shape CHECK(token_hash ~ '^[0-9a-f]{64}$')""",
        "GRANT SELECT ON users,memberships,workspaces TO hub_auth",
        "GRANT UPDATE(password_hash) ON users TO hub_auth",
        "CREATE POLICY auth_user_read ON users FOR SELECT TO hub_auth USING (true)",
        "CREATE POLICY auth_user_upgrade ON users FOR UPDATE TO hub_auth USING (active) WITH CHECK (active)",
        "CREATE POLICY auth_membership_read ON memberships FOR SELECT TO hub_auth USING (true)",
        "CREATE POLICY auth_workspace_read ON workspaces FOR SELECT TO hub_auth USING (true)",
        # Runtime must never mint/edit credential records even with a valid tenant context.
        "REVOKE INSERT,UPDATE,DELETE ON oauth_grants,tokens FROM hub_runtime",
        "GRANT SELECT ON alembic_version TO hub_auth",
    ]
    for statement in statements: op.execute(sa.text(statement))
    for table in ("oauth_clients", "auth_browser_sessions", "auth_login_limits", "oauth_codes"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY issuer_only ON {table} TO hub_auth USING(true) WITH CHECK(true)"))
        op.execute(sa.text(f"GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hub_auth"))
    for table in ("oauth_grants", "tokens"):
        op.execute(sa.text(f"CREATE POLICY issuer_only ON {table} TO hub_auth USING(true) WITH CHECK(true)"))
        op.execute(sa.text(f"GRANT SELECT,INSERT,UPDATE ON {table} TO hub_auth"))
    # The migration owner can read only the exact tables used by this definer function.
    # It has FORCE RLS and no global BYPASSRLS. No caller can obtain the owner's role.
    for table in ("users", "memberships", "oauth_clients", "oauth_grants", "tokens"):
        op.execute(sa.text(f"CREATE POLICY verifier_owner_read ON {table} FOR SELECT TO hub_migrator USING(true)"))
    op.execute(sa.text("""CREATE FUNCTION hub_access_identity(p_hash text, p_issuer text, p_resource text)
        RETURNS TABLE(token_id uuid, client_id text, user_id uuid, workspace_id uuid,
            scopes text[], expires_at bigint, issuer text, resource text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        SELECT t.id,g.client_id,g.user_id,g.workspace_id,
            ARRAY(SELECT jsonb_array_elements_text(t.scopes)),floor(extract(epoch FROM t.expires_at))::bigint,t.issuer,t.resource
        FROM public.tokens t JOIN public.oauth_grants g ON g.workspace_id=t.workspace_id AND g.id=t.grant_id
        JOIN public.memberships m ON m.workspace_id=g.workspace_id AND m.user_id=g.user_id AND m.active
        JOIN public.users u ON u.id=g.user_id AND u.active
        JOIN public.oauth_clients c ON c.client_id=g.client_id AND c.active
        WHERE t.token_hash=p_hash AND t.kind='access' AND t.revoked_at IS NULL AND t.expires_at>now()
          AND g.revoked_at IS NULL AND t.issuer=p_issuer AND g.issuer=p_issuer
          AND t.resource=p_resource AND g.resource=p_resource
          AND (c.metadata_expires_at IS NULL OR c.metadata_expires_at>now())
        $$"""))
    op.execute(sa.text("REVOKE ALL ON FUNCTION hub_access_identity(text,text,text) FROM PUBLIC"))
    op.execute(sa.text("GRANT EXECUTE ON FUNCTION hub_access_identity(text,text,text) TO hub_runtime"))
    op.execute(sa.text("CREATE INDEX oauth_codes_expiry ON oauth_codes(expires_at)"))
    op.execute(sa.text("CREATE INDEX auth_sessions_expiry ON auth_browser_sessions(expires_at)"))


def downgrade():
    raise RuntimeError("Credential history must not be destroyed by downgrade; forward-migrate instead")
