"""Operator-approved immutable runtime releases and fenced job claims."""
from alembic import op
import sqlalchemy as sa

revision='0004_g4'
down_revision='0003_g3'


def upgrade():
    for sql in [
        """CREATE TABLE document_texts(workspace_id uuid NOT NULL REFERENCES workspaces(id),resource_id uuid NOT NULL,
          logical_path text NOT NULL,source_sha256 char(64) NOT NULL,body text,body_fold text,unavailable_reason text,
          PRIMARY KEY(workspace_id,resource_id),FOREIGN KEY(workspace_id,resource_id) REFERENCES resources(workspace_id,id),
          CHECK((body IS NULL)=(body_fold IS NULL)),CHECK(octet_length(body)<=2097152))""",
        "ALTER TABLE document_texts ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE document_texts FORCE ROW LEVEL SECURITY",
        "GRANT SELECT,INSERT ON document_texts TO hub_runtime",
        """CREATE POLICY tenant_read ON document_texts FOR SELECT TO hub_runtime USING(
          workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(SELECT 1 FROM memberships m
          WHERE m.workspace_id=document_texts.workspace_id AND m.active AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))""",
        """CREATE POLICY tenant_insert ON document_texts FOR INSERT TO hub_runtime WITH CHECK(
          workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(SELECT 1 FROM memberships m
          WHERE m.workspace_id=document_texts.workspace_id AND m.active AND m.role IN ('owner','admin')
          AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))""",
        """CREATE TABLE runtime_releases(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL REFERENCES workspaces(id),
          plugin_version_id uuid NOT NULL,image_digest char(71) NOT NULL CHECK(image_digest ~ '^sha256:[0-9a-f]{64}$'),
          release_digest char(64) NOT NULL CHECK(release_digest ~ '^[0-9a-f]{64}$'),source_tree_sha256 char(64) NOT NULL,
          manifest jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(workspace_id,id),UNIQUE(workspace_id,plugin_version_id),
          FOREIGN KEY(workspace_id,plugin_version_id) REFERENCES plugin_versions(workspace_id,id))""",
        "ALTER TABLE runtime_releases ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE runtime_releases FORCE ROW LEVEL SECURITY",
        "GRANT SELECT ON runtime_releases TO hub_runtime",
        """CREATE POLICY tenant_read ON runtime_releases FOR SELECT TO hub_runtime USING(
          workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(
          SELECT 1 FROM memberships m WHERE m.workspace_id=runtime_releases.workspace_id AND m.active
          AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))""",
        "REVOKE INSERT,UPDATE,DELETE ON tool_bindings FROM hub_runtime",
        "CREATE TRIGGER immutable_binding BEFORE UPDATE OR DELETE ON tool_bindings FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()",
        "CREATE TRIGGER immutable_release BEFORE UPDATE OR DELETE ON runtime_releases FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()",
        "CREATE TRIGGER immutable_document BEFORE UPDATE OR DELETE ON document_texts FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()",
        """CREATE FUNCTION hub_job_history() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF OLD.state IN ('succeeded','failed','cancelled') AND NEW IS DISTINCT FROM OLD THEN
              RAISE EXCEPTION 'terminal job is immutable' USING ERRCODE='42501'; END IF;
            IF (NEW.workspace_id,NEW.user_id,NEW.binding_id,NEW.plugin_version_id,NEW.input,NEW.input_hash,NEW.idempotency_key,NEW.operation,NEW.project_id)
              IS DISTINCT FROM (OLD.workspace_id,OLD.user_id,OLD.binding_id,OLD.plugin_version_id,OLD.input,OLD.input_hash,OLD.idempotency_key,OLD.operation,OLD.project_id)
              THEN RAISE EXCEPTION 'job input is immutable' USING ERRCODE='42501'; END IF;
            RETURN NEW;
          END $$""",
        "CREATE TRIGGER immutable_job_history BEFORE UPDATE ON jobs FOR EACH ROW EXECUTE FUNCTION hub_job_history()",
        "REVOKE UPDATE,DELETE ON job_attempts FROM hub_runtime",
        "CREATE POLICY job_claim_owner ON jobs TO hub_migrator USING(true) WITH CHECK(true)",
        "CREATE INDEX jobs_claim_queue ON jobs(state,type,created_at)",
        """CREATE FUNCTION hub_claim_job(p_worker text) RETURNS TABLE(id uuid,workspace_id uuid,user_id uuid,lease_token uuid)
          LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
          BEGIN
            IF length(p_worker)>64 OR p_worker !~ '^[a-zA-Z0-9_-]+$' THEN RAISE EXCEPTION 'invalid worker'; END IF;
            PERFORM pg_advisory_xact_lock(470004);
            UPDATE public.jobs j SET state='failed',error_code='timeout',finished_at=now(),lease_token=NULL,lease_expires_at=NULL
              WHERE j.type='finance_light' AND (j.state='queued' OR (j.state='running' AND j.lease_expires_at<now())) AND j.deadline_at<now();
            UPDATE public.jobs j SET state=CASE WHEN j.attempts>=j.max_attempts THEN 'failed' ELSE 'queued' END,
              error_code=CASE WHEN j.attempts>=j.max_attempts THEN 'runtime_unavailable' ELSE NULL END,
              finished_at=CASE WHEN j.attempts>=j.max_attempts THEN now() ELSE NULL END,lease_token=NULL,lease_expires_at=NULL
              WHERE j.type='finance_light' AND j.state='running' AND j.lease_expires_at<now();
            UPDATE public.jobs j SET state='cancelled',finished_at=now()
              WHERE j.type='finance_light' AND j.state='queued' AND j.cancel_requested_at IS NOT NULL;
            UPDATE public.jobs j SET state='failed',error_code='forbidden',finished_at=now()
              WHERE j.type='finance_light' AND j.state='queued' AND NOT EXISTS(
                SELECT 1 FROM public.memberships m JOIN public.users u ON u.id=m.user_id AND u.active
                WHERE m.user_id=j.user_id AND m.workspace_id=j.workspace_id AND m.active AND m.role IN ('owner','admin','member'));
            RETURN QUERY UPDATE public.jobs j SET state='running',attempts=j.attempts+1,started_at=now(),
              lease_owner=p_worker,lease_token=gen_random_uuid(),heartbeat_at=now(),lease_expires_at=now()+interval '30 seconds'
              WHERE j.id=(SELECT q.id FROM public.jobs q WHERE q.state='queued' AND q.type='finance_light'
                AND q.attempts<q.max_attempts AND q.deadline_at>now() AND
                (SELECT count(*) FROM public.jobs r WHERE r.state='running' AND r.type=q.type)<2
                ORDER BY q.created_at FOR UPDATE OF q SKIP LOCKED LIMIT 1)
              RETURNING j.id,j.workspace_id,j.user_id,j.lease_token;
          END $$""",
        "REVOKE ALL ON FUNCTION hub_claim_job(text) FROM PUBLIC",
        "GRANT EXECUTE ON FUNCTION hub_claim_job(text) TO hub_runtime",
    ]:op.execute(sa.text(sql))


def downgrade():raise RuntimeError('Preserve job/release history; forward-migrate')
