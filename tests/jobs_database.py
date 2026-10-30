"""Real PostgreSQL checks after operator approval, before dispatcher starts."""
import json
from pathlib import Path
import sys
from uuid import UUID,uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from goodmcp.database import Database,Principal,NotFound,Forbidden
from goodmcp.fixtures import USER_B,WORKSPACE_B
from goodmcp.jobs import Jobs
from goodmcp.dispatcher import Dispatcher

ws,user,version=map(UUID,sys.argv[1:4]);db=Database(pool_size=2)
owner=Principal(user,frozenset({'hub:read','hub:write','tools:run'}));foreign=Principal(USER_B,frozenset({'hub:read','hub:write','tools:run'}))
checks=[]
def check(name,condition):
    assert condition,name;checks.append({'name':name,'passed':True})

with db.tenant(owner,ws) as t:
    jobs=Jobs(t,Path('/data'))
    binding=t.connection.execute(text("SELECT id FROM tool_bindings WHERE plugin_version_id=:v AND adapter_id='cit_estimate'"),{'v':version}).scalar_one()
    job=jobs.enqueue(binding,{'revenue':100,'cost':0},uuid4().hex)
    runtime=t.connection.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname='runtime_releases'")).one()
    check('release FORCE RLS',runtime==(True,True))
    check('runtime cannot approve bindings',not t.connection.execute(text("SELECT has_table_privilege(current_user,'tool_bindings','INSERT')")).scalar_one())
    check('runtime cannot approve releases',not t.connection.execute(text("SELECT has_table_privilege(current_user,'runtime_releases','INSERT')")).scalar_one())
with db.tenant(foreign,WORKSPACE_B) as t:
    try:Jobs(t,Path('/data')).get_job(job['id']);raise AssertionError('foreign job readable')
    except NotFound:pass
    try:Jobs(t,Path('/data')).binding(binding);raise AssertionError('foreign binding readable')
    except NotFound:pass
    check('foreign handles rejected',True)
with db.engine.connect() as c:
    check('contextless releases hidden',c.execute(text('SELECT count(*) FROM runtime_releases')).scalar_one()==0)
with db.engine.begin() as c:claim=c.execute(text("SELECT * FROM hub_claim_job('dbtest')")).mappings().one()
check('claim binds server-stored user and workspace',claim['id']==job['id'] and claim['workspace_id']==ws and claim['user_id']==user)
with db.tenant(owner,ws) as t:
    changed=uuid4();t.connection.execute(text("UPDATE jobs SET lease_token=:token WHERE id=:id"),{'id':job['id'],'token':changed})
release={'image_digest':'sha256:'+'0'*64,'release_digest':'0'*64}
dispatcher=Dispatcher(db,release,'g4-dbtest');dispatcher.finish(claim,error='tool_exit')
with db.tenant(owner,ws) as t:
    row=t.connection.execute(text('SELECT state,result_artifact_id FROM jobs WHERE id=:id'),{'id':job['id']}).one()
    check('stale fenced attempt cannot publish or finish',row==('running',None))
    Jobs(t,Path('/data')).cancel_job(job['id'])
    t.connection.execute(text("UPDATE jobs SET state='cancelled',finished_at=now() WHERE id=:id"),{'id':job['id']})
try:
    with db.tenant(owner,ws) as t:t.connection.execute(text("UPDATE jobs SET state='queued',finished_at=NULL WHERE id=:id"),{'id':job['id']})
    raise AssertionError('terminal job changed')
except DBAPIError as e:check('terminal job DB immutability',e.orig.sqlstate=='42501')
try:
    with db.tenant(foreign,WORKSPACE_B) as t:
        t.connection.execute(text("""INSERT INTO jobs(workspace_id,user_id,binding_id,plugin_version_id,type,operation,input_hash,idempotency_key,input,deadline_at)
          VALUES(:ws,:u,:b,:v,'finance_light','cit_estimate',:h,:k,'{}',now()+interval '1 minute')"""),
          {'ws':WORKSPACE_B,'u':USER_B,'b':binding,'v':version,'h':'0'*64,'k':uuid4().hex})
    raise AssertionError('cross tenant FK accepted')
except DBAPIError as e:check('cross-workspace binding/version FK rejected',e.orig.sqlstate=='23503')
print(json.dumps({'passed':True,'checks':checks}))
