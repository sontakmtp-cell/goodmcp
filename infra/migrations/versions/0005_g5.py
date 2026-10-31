"""Durable project files, immutable commits and truthful host reports."""
from alembic import op
import sqlalchemy as sa

revision = '0005_g5'
down_revision = '0004_g4'


def upgrade():
    statements = [
        'ALTER TABLE projects ADD COLUMN lead_user_id uuid',
        '''ALTER TABLE projects ADD CONSTRAINT project_lead_tenant FOREIGN KEY(workspace_id,lead_user_id)
           REFERENCES memberships(workspace_id,user_id)''',
        '''ALTER TABLE stage_commits ADD COLUMN input_hash char(64),
           ADD COLUMN snapshot jsonb NOT NULL DEFAULT '{}'::jsonb''',
        'ALTER TABLE projects ADD CONSTRAINT project_version_key UNIQUE(workspace_id,id,plugin_version_id)',
        'ALTER TABLE artifacts ADD CONSTRAINT artifact_project_key UNIQUE(workspace_id,project_id,id)',
        '''CREATE TABLE project_files(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL REFERENCES workspaces(id),
           project_id uuid NOT NULL,plugin_version_id uuid NOT NULL,artifact_id uuid NOT NULL,logical_path text NOT NULL,
           file_revision integer NOT NULL CHECK(file_revision>0),project_revision integer NOT NULL CHECK(project_revision>=0),
           status text NOT NULL CHECK(status IN ('draft','confirmed','state')),created_at timestamptz NOT NULL DEFAULT now(),
           UNIQUE(workspace_id,id),UNIQUE(workspace_id,project_id,logical_path,file_revision),
           FOREIGN KEY(workspace_id,project_id,plugin_version_id) REFERENCES projects(workspace_id,id,plugin_version_id),
           FOREIGN KEY(workspace_id,project_id,artifact_id) REFERENCES artifacts(workspace_id,project_id,id))''',
        '''CREATE TABLE project_operations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL REFERENCES workspaces(id),
           project_id uuid NOT NULL,operation text NOT NULL,idempotency_key text NOT NULL,input_hash char(64) NOT NULL,
           result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(workspace_id,id),
           UNIQUE(workspace_id,operation,idempotency_key),
           FOREIGN KEY(workspace_id,project_id) REFERENCES projects(workspace_id,id))''',
        "CREATE TRIGGER immutable_stage_commit BEFORE UPDATE OR DELETE ON stage_commits FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()",
        "REVOKE UPDATE,DELETE ON stage_commits FROM hub_runtime",
        '''CREATE FUNCTION hub_project_pin() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
           IF (NEW.workspace_id,NEW.plugin_version_id,NEW.lead_user_id) IS DISTINCT FROM
              (OLD.workspace_id,OLD.plugin_version_id,OLD.lead_user_id) THEN
             RAISE EXCEPTION 'project pin and lead are immutable' USING ERRCODE='42501'; END IF;
           RETURN NEW; END $$''',
        'CREATE TRIGGER immutable_project_pin BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION hub_project_pin()',
        'REVOKE UPDATE,DELETE ON host_profiles FROM hub_runtime',
        'CREATE TRIGGER immutable_host_profile BEFORE UPDATE OR DELETE ON host_profiles FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()',
    ]
    for sql in statements: op.execute(sa.text(sql))
    for table in ('project_files', 'project_operations'):
        for sql in [
            f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY',
            f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY',
            f'GRANT SELECT,INSERT ON {table} TO hub_runtime',
            f'''CREATE POLICY tenant_read ON {table} FOR SELECT TO hub_runtime USING(
                workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(
                SELECT 1 FROM memberships m WHERE m.workspace_id={table}.workspace_id AND m.active
                AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))''',
            f'''CREATE POLICY tenant_insert ON {table} FOR INSERT TO hub_runtime WITH CHECK(
                workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(
                SELECT 1 FROM projects p WHERE p.workspace_id={table}.workspace_id AND p.id={table}.project_id
                AND p.lead_user_id=NULLIF(current_setting('app.user_id',true),'')::uuid) AND EXISTS(
                SELECT 1 FROM memberships m WHERE m.workspace_id={table}.workspace_id AND m.active
                AND m.role IN ('owner','admin','member') AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))''',
            f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()',
            f'CREATE INDEX ix_{table}_workspace ON {table}(workspace_id)',
        ]: op.execute(sa.text(sql))
    op.execute(sa.text('CREATE INDEX project_files_latest ON project_files(workspace_id,project_id,logical_path,file_revision DESC)'))


def downgrade():
    raise RuntimeError('Preserve project history; forward-migrate')
