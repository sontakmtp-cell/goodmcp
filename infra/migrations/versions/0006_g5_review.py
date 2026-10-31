"""Explicit, audited ownership recovery for projects predating G5. No inferred leads."""
from alembic import op
import sqlalchemy as sa

revision = '0006_g5_review'
down_revision = '0005_g5'


def upgrade():
    for statement in [
        '''CREATE TABLE project_lead_assignments(
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL REFERENCES workspaces(id),
            project_id uuid NOT NULL,lead_user_id uuid NOT NULL,confirmed_by_user_id uuid NOT NULL,
            evidence text NOT NULL CHECK(length(btrim(evidence)) BETWEEN 10 AND 4000),
            created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(workspace_id,id),UNIQUE(workspace_id,project_id),
            FOREIGN KEY(workspace_id,project_id) REFERENCES projects(workspace_id,id),
            FOREIGN KEY(workspace_id,lead_user_id) REFERENCES memberships(workspace_id,user_id),
            FOREIGN KEY(workspace_id,confirmed_by_user_id) REFERENCES memberships(workspace_id,user_id))''',
        'ALTER TABLE project_lead_assignments ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE project_lead_assignments FORCE ROW LEVEL SECURITY',
        'GRANT SELECT ON project_lead_assignments TO hub_runtime',
        '''CREATE POLICY tenant_read ON project_lead_assignments FOR SELECT TO hub_runtime USING(
            workspace_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid AND EXISTS(
            SELECT 1 FROM memberships m WHERE m.workspace_id=project_lead_assignments.workspace_id
            AND m.active AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid))''',
        '''CREATE TRIGGER immutable_project_lead_assignment BEFORE UPDATE OR DELETE ON project_lead_assignments
            FOR EACH ROW EXECUTE FUNCTION hub_immutable_source()''',
        '''CREATE OR REPLACE FUNCTION hub_project_pin() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF (NEW.workspace_id,NEW.plugin_version_id) IS DISTINCT FROM (OLD.workspace_id,OLD.plugin_version_id) THEN
                RAISE EXCEPTION 'project pin is immutable' USING ERRCODE='42501'; END IF;
            IF NEW.lead_user_id IS DISTINCT FROM OLD.lead_user_id THEN
                IF OLD.lead_user_id IS NOT NULL OR NEW.lead_user_id IS NULL OR NOT EXISTS(
                    SELECT 1 FROM project_lead_assignments a WHERE a.workspace_id=OLD.workspace_id
                    AND a.project_id=OLD.id AND a.lead_user_id=NEW.lead_user_id) THEN
                    RAISE EXCEPTION 'lead requires an operator-confirmed legacy assignment' USING ERRCODE='42501';
                END IF;
            END IF;
            RETURN NEW; END $$''',
        '''CREATE FUNCTION hub_assign_legacy_project_lead(p_workspace uuid,p_project uuid,p_lead uuid,
            p_confirmed_by uuid,p_evidence text) RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER
            SET search_path=pg_catalog,public AS $$
            DECLARE current_lead uuid; assignment public.project_lead_assignments%ROWTYPE; new_id uuid;
            BEGIN
                IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper) THEN
                    RAISE EXCEPTION 'operator admin required' USING ERRCODE='42501'; END IF;
                IF p_evidence IS NULL OR length(btrim(p_evidence)) NOT BETWEEN 10 AND 4000 THEN
                    RAISE EXCEPTION 'ownership confirmation evidence required' USING ERRCODE='22023'; END IF;
                IF NOT EXISTS(SELECT 1 FROM public.memberships m JOIN public.users u ON u.id=m.user_id AND u.active
                    WHERE m.workspace_id=p_workspace AND m.user_id=p_confirmed_by AND m.active AND m.role='owner') THEN
                    RAISE EXCEPTION 'active workspace owner confirmation required' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS(SELECT 1 FROM public.memberships m JOIN public.users u ON u.id=m.user_id AND u.active
                    WHERE m.workspace_id=p_workspace AND m.user_id=p_lead AND m.active AND m.role IN ('owner','admin','member')) THEN
                    RAISE EXCEPTION 'lead must be an active writable member in this workspace' USING ERRCODE='42501'; END IF;
                SELECT lead_user_id INTO current_lead FROM public.projects WHERE workspace_id=p_workspace AND id=p_project FOR UPDATE;
                IF NOT FOUND THEN RAISE EXCEPTION 'project not found' USING ERRCODE='P0002'; END IF;
                SELECT * INTO assignment FROM public.project_lead_assignments WHERE workspace_id=p_workspace AND project_id=p_project;
                IF FOUND AND current_lead=p_lead AND assignment.lead_user_id=p_lead
                    AND assignment.confirmed_by_user_id=p_confirmed_by AND assignment.evidence=p_evidence THEN RETURN assignment.id; END IF;
                IF current_lead IS NOT NULL OR assignment.id IS NOT NULL THEN
                    RAISE EXCEPTION 'project already has a lead or conflicting assignment' USING ERRCODE='23505'; END IF;
                INSERT INTO public.project_lead_assignments(workspace_id,project_id,lead_user_id,confirmed_by_user_id,evidence)
                    VALUES(p_workspace,p_project,p_lead,p_confirmed_by,p_evidence) RETURNING id INTO new_id;
                UPDATE public.projects SET lead_user_id=p_lead WHERE workspace_id=p_workspace AND id=p_project;
                INSERT INTO public.audit_events(workspace_id,user_id,action,request_id,details)
                    VALUES(p_workspace,p_confirmed_by,'legacy_project_lead_assigned',gen_random_uuid(),
                        jsonb_build_object('project_id',p_project,'assignment_id',new_id,'lead_user_id',p_lead));
                RETURN new_id;
            END $$''',
        'REVOKE ALL ON FUNCTION hub_assign_legacy_project_lead(uuid,uuid,uuid,uuid,text) FROM PUBLIC',
    ]: op.execute(sa.text(statement))


def downgrade():
    raise RuntimeError('Preserve ownership evidence; forward-migrate')
