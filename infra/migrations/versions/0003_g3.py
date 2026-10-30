"""Tenant-bound resumable upload queue and immutable registry."""
from alembic import op
import sqlalchemy as sa

revision = "0003_g3"
down_revision = "0002_g2"


def upgrade():
    statements = [
        """CREATE TABLE plugin_uploads (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id),
          user_id uuid NOT NULL, idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 100),
          sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), bytes bigint NOT NULL CHECK(bytes BETWEEN 1 AND 1073741824),
          state text NOT NULL DEFAULT 'uploading' CHECK(state IN ('uploading','queued','scanning','ready','rejected','cancelled')),
          source_artifact_id uuid, plugin_version_id uuid, preview jsonb NOT NULL DEFAULT '{}', error_code text,
          attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3), lease_token uuid, lease_until timestamptz,
          expires_at timestamptz NOT NULL DEFAULT now()+interval '24 hours', created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(workspace_id,id), UNIQUE(workspace_id,idempotency_key),
          FOREIGN KEY(workspace_id,user_id) REFERENCES memberships(workspace_id,user_id),
          FOREIGN KEY(workspace_id,source_artifact_id) REFERENCES artifacts(workspace_id,id),
          FOREIGN KEY(workspace_id,plugin_version_id) REFERENCES plugin_versions(workspace_id,id))""",
        """CREATE TABLE plugin_upload_parts (
          workspace_id uuid NOT NULL REFERENCES workspaces(id), upload_id uuid NOT NULL, part integer NOT NULL CHECK(part BETWEEN 0 AND 127),
          artifact_id uuid NOT NULL, PRIMARY KEY(workspace_id,upload_id,part),
          FOREIGN KEY(workspace_id,upload_id) REFERENCES plugin_uploads(workspace_id,id),
          FOREIGN KEY(workspace_id,artifact_id) REFERENCES artifacts(workspace_id,id))""",
        "CREATE INDEX plugin_upload_queue ON plugin_uploads(state,created_at)",
        "ALTER TABLE installations ADD COLUMN package_id uuid, ADD COLUMN revision integer NOT NULL DEFAULT 1 CHECK(revision>0)",
        "UPDATE installations i SET package_id=v.package_id FROM plugin_versions v WHERE v.id=i.plugin_version_id AND v.workspace_id=i.workspace_id",
        "ALTER TABLE installations ALTER COLUMN package_id SET NOT NULL",
        "ALTER TABLE installations ADD CONSTRAINT fk_installation_package FOREIGN KEY(workspace_id,package_id) REFERENCES plugin_packages(workspace_id,id)",
        "CREATE UNIQUE INDEX one_installation_per_package ON installations(workspace_id,package_id)",
        # Existing G2 owner read policies on users/memberships support this narrow queue claim.
        "CREATE POLICY importer_owner ON plugin_uploads TO hub_migrator USING(true) WITH CHECK(true)",
    ]
    for s in statements: op.execute(sa.text(s))
    uid = "NULLIF(current_setting('app.user_id',true),'')::uuid"
    wid = "NULLIF(current_setting('app.workspace_id',true),'')::uuid"
    for table in ("plugin_uploads", "plugin_upload_parts"):
        readable = f"workspace_id={wid} AND EXISTS(SELECT 1 FROM memberships m WHERE m.workspace_id={table}.workspace_id AND m.user_id={uid} AND m.active)"
        writable = f"({readable}) AND EXISTS(SELECT 1 FROM memberships m WHERE m.workspace_id={table}.workspace_id AND m.user_id={uid} AND m.active AND m.role IN ('owner','admin'))"
        for s in (f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
                  f"GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hub_runtime",
                  f"CREATE POLICY tenant_read ON {table} FOR SELECT TO hub_runtime USING({readable})",
                  f"CREATE POLICY tenant_insert ON {table} FOR INSERT TO hub_runtime WITH CHECK({writable})",
                  f"CREATE POLICY tenant_update ON {table} FOR UPDATE TO hub_runtime USING({writable}) WITH CHECK({writable})",
                  f"CREATE POLICY tenant_delete ON {table} FOR DELETE TO hub_runtime USING({writable})"):
            op.execute(sa.text(s))
    op.execute(sa.text("""CREATE FUNCTION hub_claim_import() RETURNS TABLE(id uuid,workspace_id uuid,user_id uuid,lease_token uuid)
      LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        UPDATE public.plugin_uploads SET state='rejected',error_code='import_retry_exhausted',lease_until=NULL
          WHERE state='scanning' AND lease_until<now() AND attempts>=3;
        UPDATE public.plugin_uploads SET state='rejected',error_code='upload_expired',lease_until=NULL
          WHERE state IN ('queued','scanning') AND expires_at<=now();
        UPDATE public.plugin_uploads u SET state='scanning',attempts=attempts+1,
          lease_token=gen_random_uuid(),lease_until=now()+interval '30 minutes'
        WHERE u.id=(SELECT q.id FROM public.plugin_uploads q
          JOIN public.memberships m ON m.workspace_id=q.workspace_id AND m.user_id=q.user_id AND m.active AND m.role IN ('owner','admin')
          JOIN public.users x ON x.id=q.user_id AND x.active
          WHERE (q.state='queued' OR (q.state='scanning' AND q.lease_until<now())) AND q.attempts<3 AND q.expires_at>now()
          ORDER BY q.created_at FOR UPDATE OF q SKIP LOCKED LIMIT 1)
        RETURNING u.id,u.workspace_id,u.user_id,u.lease_token
      $$"""))
    op.execute(sa.text("REVOKE ALL ON FUNCTION hub_claim_import() FROM PUBLIC"))
    op.execute(sa.text("GRANT EXECUTE ON FUNCTION hub_claim_import() TO hub_runtime"))
    # Published versions and normalized source rows cannot be mutated through runtime SQL.
    # Future migrations can intentionally replace this trigger for a schema evolution.
    op.execute(sa.text("""CREATE FUNCTION hub_immutable_source() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'immutable plugin source' USING ERRCODE='42501'; END $$"""))
    for table in ("plugin_versions", "skills", "agents", "resources"):
        op.execute(sa.text(f"CREATE TRIGGER immutable_source BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()"))


def downgrade():
    raise RuntimeError("Keep immutable source history; forward-migrate")
