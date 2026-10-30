"""Workspace-authorized asynchronous adapter calls, immutable input and results."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from uuid import UUID, uuid4
from sqlalchemy import text
from .database import Forbidden, NotFound
from .registry import Registry
from .storage import Conflict
from .finance_spec import validate


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class QueueQuota(Conflict):pass


class Jobs(Registry):
    def run_permission(self):
        if self.t.context.role not in ('owner','admin','member') or 'tools:run' not in self.t.context.scopes:
            raise Forbidden('tools:run and active member required')

    def bindings(self,installation_id):
        v=self.active_version(installation_id)
        return [dict(r) for r in self.c.execute(text("SELECT id,mcp_name,input_schema,output_schema,limits FROM tool_bindings WHERE workspace_id=:ws AND plugin_version_id=:v ORDER BY mcp_name"),self._params(v=v['id'])).mappings()]

    def binding(self,binding_id):
        row=self.c.execute(text("""SELECT b.*,r.release_digest,r.source_tree_sha256 FROM tool_bindings b
          JOIN runtime_releases r ON r.workspace_id=b.workspace_id AND r.plugin_version_id=b.plugin_version_id AND r.image_digest=b.image_digest
          JOIN installations i ON i.workspace_id=b.workspace_id AND i.plugin_version_id=b.plugin_version_id AND i.enabled
          WHERE b.workspace_id=:ws AND b.id=:id"""),self._params(id=UUID(str(binding_id)))).mappings().one_or_none()
        if row is None:raise NotFound('Approved enabled binding not found')
        return row

    def operation_binding(self,installation_id,operation):
        v=self.active_version(installation_id)
        result=self.c.execute(text("SELECT id FROM tool_bindings WHERE workspace_id=:ws AND plugin_version_id=:v AND adapter_id=:op"),self._params(v=v['id'],op=operation)).scalar_one_or_none()
        if result is None:raise NotFound('Runtime not approved for this version')
        return result

    def enqueue(self,binding_id,arguments,idempotency_key,project_id=None):
        self.run_permission();b=self.binding(binding_id)
        if not 1<=len(idempotency_key)<=100:raise ValueError('Invalid idempotency key')
        if b['adapter_id']=='_probe':
            if set(arguments)!= {'kind'} or arguments['kind'] not in ('sleep','crash','boundaries'):raise ValueError('Invalid probe')
            args=arguments
        else:args=validate(b['adapter_id'],arguments)
        if len(canonical(args).encode())>16384:raise ValueError('Arguments too large')
        if project_id:
            if 'projects:write' not in self.t.context.scopes:raise Forbidden('projects:write required for project output')
            project=self.c.execute(text("SELECT plugin_version_id FROM projects WHERE workspace_id=:ws AND id=:p"),self._params(p=project_id)).one_or_none()
            if project is None:raise NotFound('Project not found')
            if project[0]!=b['plugin_version_id']:raise Conflict('Project pins a different version')
        input_hash=hashlib.sha256(canonical({'binding':str(b['id']),'version':str(b['plugin_version_id']),'args':args,'project':str(project_id) if project_id else None}).encode()).hexdigest()
        self.c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,4))"),{'key':str(self.ws)})
        old=self.c.execute(text("SELECT id,input_hash FROM jobs WHERE workspace_id=:ws AND operation=:op AND idempotency_key=:key"),self._params(op=b['adapter_id'],key=idempotency_key)).mappings().one_or_none()
        if old:
            if old['input_hash']!=input_hash:raise Conflict('Idempotency key conflicts with existing input')
            return self.get_job(old['id'])
        count=self.c.execute(text("SELECT count(*) FROM jobs WHERE workspace_id=:ws AND state IN ('queued','running')"),self._params()).scalar_one()
        if count>=20:raise QueueQuota('Workspace queue quota reached')
        job=uuid4();kind='finance_light'
        self.c.execute(text("""INSERT INTO jobs(id,workspace_id,user_id,project_id,plugin_version_id,binding_id,type,operation,input_hash,idempotency_key,input,deadline_at)
          VALUES(:id,:ws,:u,:p,:v,:b,:type,:op,:hash,:key,CAST(:input AS jsonb),:deadline)"""),self._params(id=job,u=self.t.context.user_id,p=project_id,
          v=b['plugin_version_id'],b=b['id'],type=kind,op=b['adapter_id'],hash=input_hash,key=idempotency_key,input=canonical(args),deadline=datetime.now(timezone.utc)+timedelta(minutes=10)))
        self.audit('tool_job_queued',{'job_id':str(job),'binding_id':str(b['id'])})
        return self.get_job(job)

    def get_job(self,job_id):
        row=self.c.execute(text("SELECT * FROM jobs WHERE workspace_id=:ws AND id=:id"),self._params(id=UUID(str(job_id)))).mappings().one_or_none()
        if row is None:raise NotFound('Job not found')
        result={k:row[k] for k in ('id','state','operation','attempts','created_at','started_at','finished_at','result_artifact_id')}
        result['error']={'code':row['error_code'],'retryable':False} if row['error_code'] else None
        result['cancel_requested']=row['cancel_requested_at'] is not None
        if row['state']=='succeeded':result['result']=json.loads(b''.join(self.store.stream(row['result_artifact_id'])))
        return result

    def cancel_job(self,job_id):
        self.run_permission();job=self.get_job(job_id)
        self.c.execute(text("""UPDATE jobs SET cancel_requested_at=now(),
          state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
          finished_at=CASE WHEN state='queued' THEN now() ELSE finished_at END
          WHERE workspace_id=:ws AND id=:id AND state IN ('queued','running')"""),self._params(id=job['id']))
        return self.get_job(job_id)
