"""Privileged local dispatcher. Only this service has Docker socket access.

Runtime containers have no network, mounts, secrets or DB credentials. Config is
an operator-approved release, never supplied by an invocation or uploaded plugin.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import signal
import threading
import time
from uuid import uuid4
from sqlalchemy import text
from .database import Database, Principal
from .docker_engine import Engine
from .jobs import Jobs, canonical


class Dispatcher:
    def __init__(self,database,release,project):
        self.db,self.release,self.project=database,release,project
        self.engine=Engine();self.stop=threading.Event();self.lock=threading.Lock()

    def tenant(self,claim):return self.db.tenant(Principal(claim['user_id'],frozenset({'hub:read','hub:write','tools:run'})),claim['workspace_id'])

    def beat(self,claim):
        with self.tenant(claim) as t:
            row=t.connection.execute(text("""UPDATE jobs SET heartbeat_at=now(),lease_expires_at=now()+interval '30 seconds'
                WHERE workspace_id=:ws AND id=:id AND state='running' AND lease_token=:lease AND lease_expires_at>now()
                RETURNING cancel_requested_at,deadline_at"""),{'ws':claim['workspace_id'],'id':claim['id'],'lease':claim['lease_token']}).one_or_none()
            if row is None:raise RuntimeError('fenced')
            if row[0] is not None:return 'cancelled'
            # Revalidate membership and current installation on every heartbeat.
            jobs=Jobs(t,Path(os.environ.get('HUB_STORAGE_ROOT','/data')))
            binding=t.connection.execute(text('SELECT binding_id FROM jobs WHERE id=:id'),{'id':claim['id']}).scalar_one()
            jobs.binding(binding)
            return None

    def finish(self,claim,result=None,error=None,retry=False):
        with self.tenant(claim) as t:
            row=t.connection.execute(text("SELECT * FROM jobs WHERE workspace_id=:ws AND id=:id FOR UPDATE"),{'ws':claim['workspace_id'],'id':claim['id']}).mappings().one()
            if row['state']!='running' or row['lease_token']!=claim['lease_token']:return
            valid=t.connection.execute(text('SELECT :expires>now()'),{'expires':row['lease_expires_at']}).scalar_one()
            if not valid:return
            jobs=Jobs(t,Path(os.environ.get('HUB_STORAGE_ROOT','/data')))
            if row['cancel_requested_at'] is not None:result=None;error='cancelled';retry=False
            artifact=None
            if result is not None:
                binding=jobs.binding(row['binding_id'])
                result['provenance']={'plugin_version_id':str(row['plugin_version_id']),'source_tree_sha256':binding['source_tree_sha256'],
                    'adapter_id':row['operation'],'image_digest':binding['image_digest'],'release_digest':binding['release_digest'],
                    'source_date':'unknown','original_python':True}
                artifact=jobs.store.put([canonical(result).encode()],'application/json',max_bytes=2*1024*1024,project_id=row['project_id']).id
            retry=retry and row['attempts']<row['max_attempts'] and error!='cancelled'
            state='succeeded' if artifact else 'queued' if retry else 'cancelled' if error=='cancelled' else 'failed'
            t.connection.execute(text("""UPDATE jobs SET state=:state,result_artifact_id=:artifact,error_code=:error,
              finished_at=CASE WHEN :state='queued' THEN NULL ELSE now() END,lease_token=NULL,lease_expires_at=NULL
              WHERE workspace_id=:ws AND id=:id AND lease_token=:lease"""),{'state':state,'artifact':artifact,'error':None if state in ('queued','cancelled','succeeded') else error or 'runtime_unavailable',
                'ws':claim['workspace_id'],'id':claim['id'],'lease':claim['lease_token']})
            t.connection.execute(text("""INSERT INTO job_attempts(workspace_id,job_id,attempt,lease_token,result)
              VALUES(:ws,:id,:attempt,:lease,CAST(:result AS jsonb)) ON CONFLICT DO NOTHING"""),{'ws':claim['workspace_id'],'id':claim['id'],
                'attempt':row['attempts'],'lease':claim['lease_token'],'result':canonical({'state':state,'error':error})})


    def run(self,claim):
        container=None
        try:
            with self.tenant(claim) as t:
                row=t.connection.execute(text('SELECT * FROM jobs WHERE id=:id'),{'id':claim['id']}).mappings().one()
                binding=Jobs(t,Path('/data')).binding(row['binding_id'])
                if binding['image_digest']!=self.release['image_digest'] or binding['release_digest']!=self.release['release_digest']:
                    raise ValueError('Unapproved calculator release')
                payload={'operation':row['operation'],'arguments':row['input']};timeout=binding['limits']['timeout_s']
            start=time.monotonic();last_beat=0;error=None;result=None
            container=self.engine.create(self.project,self.project+'-'+str(claim['id'])+'-'+str(row['attempts']),self.release['image_digest'],payload=payload)
            while True:
                if self.stop.is_set():error='runtime_unavailable';break
                if time.monotonic()-start>timeout:error='timeout';break
                if time.monotonic()-last_beat>5:
                    error=self.beat(claim);last_beat=time.monotonic()
                    if error:break
                state=self.engine.inspect(container)['State']
                if not state['Running']:result=self.engine.output(container);break
                time.sleep(0.2)
            # Stop/remove the entire container before publishing a terminal cancellation/timeout.
            self.engine.remove(container);container=None
            if error:self.finish(claim,error=error,retry=error=='runtime_unavailable')
            elif not result.get('ok'):self.finish(claim,error=result.get('error','tool_exit'))
            else:self.finish(claim,result=result)
        except Exception as exc:
            code=str(exc) if str(exc) in ('tool_exit','oom','fenced') else 'runtime_unavailable'
            if container:
                try:self.engine.remove(container)
                except Exception:pass
                container=None
            try:self.finish(claim,error=code,retry=code=='runtime_unavailable')
            except Exception:pass
        finally:
            if container:
                try:self.engine.remove(container)
                except Exception:pass

    def loop(self):
        for container in self.engine.containers(self.project):self.engine.remove(container['Id'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=[]
            while not self.stop.is_set():
                pending=[f for f in pending if not f.done()]
                if len(pending)<2:
                    try:
                        with self.db.engine.begin() as c:claim=c.execute(text("SELECT * FROM hub_claim_job('dispatcher')")).mappings().one_or_none()
                        if claim:pending.append(pool.submit(self.run,claim))
                    except Exception:pass
                self.stop.wait(0.2)
        for container in self.engine.containers(self.project):self.engine.remove(container['Id'])


def main():
    release=json.loads(Path('/release/release.json').read_text())
    if release.get('mode')!='python-calculators-keyword-mvp':raise ValueError('Use the approved MVP calculator release')
    project=os.environ['HUB_RUNNER_PROJECT']
    if not project or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in project):raise ValueError('Invalid project namespace')
    dispatcher=Dispatcher(Database(pool_size=5),release,project)
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:dispatcher.stop.set())
    dispatcher.loop()


if __name__=='__main__':main()
