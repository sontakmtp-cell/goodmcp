"""Google identities, browser sessions and workspace administration; additive upgrade."""
from alembic import op
import sqlalchemy as sa

revision = '0007_g9'
down_revision = '0006_g5_review'


def upgrade():
    statements = [
        "ALTER TABLE users ADD COLUMN name text NOT NULL DEFAULT '', ADD COLUMN email_verified boolean NOT NULL DEFAULT false, ADD COLUMN platform_admin boolean NOT NULL DEFAULT false",
        # Distinct Google subjects may share an email. Email is never an identity key.
        "ALTER TABLE users DROP CONSTRAINT users_email_key",
        "CREATE UNIQUE INDEX legacy_login_email ON users(lower(email)) WHERE password_hash <> '!'",
        "ALTER TABLE workspaces ADD COLUMN archived_at timestamptz",
        "ALTER TABLE auth_browser_sessions ADD COLUMN selected_workspace_id uuid REFERENCES workspaces(id), ADD COLUMN email_verified boolean NOT NULL DEFAULT false",
        """CREATE TABLE user_identities(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid NOT NULL REFERENCES users(id),
            provider text NOT NULL CHECK(provider='google'),subject text NOT NULL,email text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(provider,subject),UNIQUE(user_id,provider))""",
        """CREATE TABLE auth_google_flows(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),state_hash char(64) UNIQUE NOT NULL,
            session_id uuid NOT NULL REFERENCES auth_browser_sessions(id) ON DELETE CASCADE,link_user_id uuid REFERENCES users(id),
            expires_at timestamptz NOT NULL,consumed_at timestamptz)""",
        """CREATE TABLE workspace_invitations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL REFERENCES workspaces(id),
            email text NOT NULL,role text NOT NULL CHECK(role IN ('admin','member','viewer')),token_hash char(64) NOT NULL UNIQUE,
            created_by uuid NOT NULL REFERENCES users(id),expires_at timestamptz NOT NULL,accepted_at timestamptz,revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE email_outbox(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),recipient text NOT NULL,subject text NOT NULL,body text NOT NULL,
            attempts integer NOT NULL DEFAULT 0,next_attempt_at timestamptz NOT NULL DEFAULT now(),sent_at timestamptz,last_error text,
            created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE platform_audit_events(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),actor_user_id uuid NOT NULL REFERENCES users(id),
            action text NOT NULL,details jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now())""",
        "DROP POLICY auth_user_upgrade ON users",
        "CREATE POLICY auth_user_manage ON users TO hub_auth USING(true) WITH CHECK(true)",
        "GRANT SELECT,INSERT,UPDATE ON users,workspaces,memberships TO hub_auth",
        "CREATE POLICY auth_workspace_manage ON workspaces TO hub_auth USING(true) WITH CHECK(true)",
        "CREATE POLICY auth_membership_manage ON memberships TO hub_auth USING(true) WITH CHECK(true)",
        "GRANT SELECT,INSERT ON audit_events TO hub_auth",
        "CREATE POLICY auth_audit ON audit_events TO hub_auth USING(true) WITH CHECK(true)",
        "GRANT SELECT,UPDATE ON jobs TO hub_auth",
        "CREATE POLICY auth_jobs ON jobs TO hub_auth USING(true) WITH CHECK(true)",
        # Enforce exactly one active owner at COMMIT, allowing an atomic transfer.
        "CREATE POLICY owner_guard_read ON memberships TO hub_migrator USING(true) WITH CHECK(true)",
        "CREATE POLICY owner_workspace_guard_read ON workspaces TO hub_migrator USING(true) WITH CHECK(true)",
        """CREATE FUNCTION hub_one_owner() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
          DECLARE ws uuid; n integer;
          BEGIN
            IF TG_TABLE_NAME='workspaces' THEN ws=NEW.id;
            ELSIF TG_OP='DELETE' THEN ws=OLD.workspace_id;
            ELSE ws=NEW.workspace_id; END IF;
            PERFORM 1 FROM public.workspaces WHERE id=ws FOR UPDATE;
            IF FOUND THEN
              SELECT count(*) INTO n FROM public.memberships WHERE workspace_id=ws AND active AND role='owner';
              IF n<>1 THEN RAISE EXCEPTION 'workspace requires exactly one owner' USING ERRCODE='23514'; END IF;
            END IF;
            RETURN NULL;
          END $$""",
        "REVOKE ALL ON FUNCTION hub_one_owner() FROM PUBLIC",
        "CREATE CONSTRAINT TRIGGER one_owner_membership AFTER INSERT OR UPDATE OR DELETE ON memberships DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hub_one_owner()",
        "CREATE CONSTRAINT TRIGGER one_owner_workspace AFTER INSERT ON workspaces DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hub_one_owner()",
        # Database-enforced revocation also covers operator changes and concurrent workers.
        """CREATE FUNCTION hub_membership_revoke() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
          BEGIN
            IF (OLD.active AND NOT NEW.active) OR NEW.role IS DISTINCT FROM OLD.role THEN
              UPDATE public.oauth_grants SET revoked_at=COALESCE(revoked_at,now()) WHERE workspace_id=NEW.workspace_id AND user_id=NEW.user_id;
              UPDATE public.tokens t SET revoked_at=COALESCE(t.revoked_at,now()) FROM public.oauth_grants g
                WHERE t.grant_id=g.id AND g.workspace_id=NEW.workspace_id AND g.user_id=NEW.user_id;
              UPDATE public.jobs SET cancel_requested_at=now(),state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
                finished_at=CASE WHEN state='queued' THEN now() ELSE finished_at END
                WHERE workspace_id=NEW.workspace_id AND user_id=NEW.user_id AND state IN ('queued','running');
            END IF; RETURN NEW;
          END $$""",
        "REVOKE ALL ON FUNCTION hub_membership_revoke() FROM PUBLIC",
        "CREATE TRIGGER membership_revoke AFTER UPDATE OF active,role ON memberships FOR EACH ROW EXECUTE FUNCTION hub_membership_revoke()",
    ]
    for statement in statements:
        op.execute(sa.text(statement))
    for table in ('user_identities','auth_google_flows','workspace_invitations','email_outbox','platform_audit_events'):
        for statement in (f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY', f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY',
                          f'CREATE POLICY issuer_only ON {table} TO hub_auth USING(true) WITH CHECK(true)',
                          f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hub_auth'):
            op.execute(sa.text(statement))
    # Trigger function runs under the migration role, with only the tables it needs.
    for table in ('oauth_grants','tokens','jobs'):
        op.execute(sa.text(f'CREATE POLICY revocation_guard ON {table} TO hub_migrator USING(true) WITH CHECK(true)'))
    op.execute(sa.text('GRANT SELECT,UPDATE ON oauth_grants,tokens,jobs TO hub_migrator'))
    op.execute(sa.text('CREATE POLICY session_revocation_guard ON auth_browser_sessions TO hub_migrator USING(true) WITH CHECK(true)'))
    op.execute(sa.text('GRANT SELECT,DELETE ON auth_browser_sessions TO hub_migrator'))
    op.execute(sa.text("""CREATE FUNCTION hub_user_revoke() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        BEGIN
          IF OLD.active AND NOT NEW.active THEN
            DELETE FROM public.auth_browser_sessions WHERE user_id=NEW.id;
            UPDATE public.oauth_grants SET revoked_at=COALESCE(revoked_at,now()) WHERE user_id=NEW.id;
            UPDATE public.tokens t SET revoked_at=COALESCE(t.revoked_at,now()) FROM public.oauth_grants g
              WHERE t.grant_id=g.id AND g.user_id=NEW.id;
            UPDATE public.jobs SET cancel_requested_at=now(),state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
              finished_at=CASE WHEN state='queued' THEN now() ELSE finished_at END WHERE user_id=NEW.id AND state IN ('queued','running');
          END IF; RETURN NEW;
        END $$"""))
    op.execute(sa.text('REVOKE ALL ON FUNCTION hub_user_revoke() FROM PUBLIC'))
    op.execute(sa.text('CREATE TRIGGER user_revoke AFTER UPDATE OF active ON users FOR EACH ROW EXECUTE FUNCTION hub_user_revoke()'))
    # Keep the resource-server function narrow; archived workspaces reject old tokens.
    op.execute(sa.text("""CREATE OR REPLACE FUNCTION hub_access_identity(p_hash text,p_issuer text,p_resource text)
        RETURNS TABLE(token_id uuid,client_id text,user_id uuid,workspace_id uuid,scopes text[],expires_at bigint,issuer text,resource text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        SELECT t.id,g.client_id,g.user_id,g.workspace_id,ARRAY(SELECT jsonb_array_elements_text(t.scopes)),
          floor(extract(epoch FROM t.expires_at))::bigint,t.issuer,t.resource
        FROM public.tokens t JOIN public.oauth_grants g ON g.workspace_id=t.workspace_id AND g.id=t.grant_id
        JOIN public.memberships m ON m.workspace_id=g.workspace_id AND m.user_id=g.user_id AND m.active
        JOIN public.users u ON u.id=g.user_id AND u.active
        JOIN public.workspaces w ON w.id=g.workspace_id AND w.archived_at IS NULL
        JOIN public.oauth_clients c ON c.client_id=g.client_id AND c.active
        WHERE t.token_hash=p_hash AND t.kind='access' AND t.revoked_at IS NULL AND t.expires_at>now()
          AND g.revoked_at IS NULL AND t.issuer=p_issuer AND g.issuer=p_issuer
          AND t.resource=p_resource AND g.resource=p_resource
          AND (c.metadata_expires_at IS NULL OR c.metadata_expires_at>now()) $$"""))
    op.execute(sa.text('CREATE INDEX invitation_workspace ON workspace_invitations(workspace_id,expires_at)'))
    op.execute(sa.text('CREATE INDEX pending_mail ON email_outbox(next_attempt_at) WHERE sent_at IS NULL'))
    # G9 explicitly shares projects within a workspace, with no project-level ACL.
    for table in ('project_files', 'project_operations'):
        op.execute(sa.text(f'DROP POLICY tenant_insert ON {table}'))
        op.execute(sa.text(f"""CREATE POLICY tenant_insert ON {table} FOR INSERT TO hub_runtime WITH CHECK(
            workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(
            SELECT 1 FROM memberships m WHERE m.workspace_id={table}.workspace_id AND m.active
            AND m.role IN ('owner','admin','member') AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))"""))


def downgrade():
    raise RuntimeError('Keep identity and membership history; forward migrate or restore')
