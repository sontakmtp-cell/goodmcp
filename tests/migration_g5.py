"""G4 database with real old data -> G5 ownership recovery, in an isolated test DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4
from psycopg import sql
from sqlalchemy import text
from goodmcp.admin import connect
from goodmcp.database import Database, Principal
from goodmcp.project_admin import assign, unassigned
from goodmcp.storage import ArtifactStore, Conflict
from goodmcp.workflows import Workflows
from goodmcp.workflow_spec import STAGES, SKILLS

DB_NAME='goodmcp_g5_upgrade'
WS=UUID('20000000-0000-4000-8000-000000000901')
WS_OTHER=UUID('20000000-0000-4000-8000-000000000902')
OWNER=UUID('10000000-0000-4000-8000-000000000901')
MEMBER=UUID('10000000-0000-4000-8000-000000000902')
FOREIGN=UUID('10000000-0000-4000-8000-000000000903')
VIEWER=UUID('10000000-0000-4000-8000-000000000904')
INACTIVE=UUID('10000000-0000-4000-8000-000000000905')
PROJECT=UUID('30000000-0000-4000-8000-000000000901')
UNRESOLVED=UUID('30000000-0000-4000-8000-000000000902')
SCOPES=frozenset({'hub:read','hub:write','projects:read','projects:write'})
MARKER=Path('/data/g5-upgrade-fixture.json')
checks=[]


def check(name, condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition: raise AssertionError(name)


def database_operation(create):
    if os.environ.get('HUB_DB_NAME')==DB_NAME: raise RuntimeError('Use primary isolated test DB for create/drop')
    with connect() as conn:
        conn.autocommit=True
        if create:
            conn.execute(sql.SQL('CREATE DATABASE {} OWNER hub_migrator').format(sql.Identifier(DB_NAME)))
            conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(DB_NAME)))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO hub_migrator,hub_runtime').format(sql.Identifier(DB_NAME)))
        else:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(DB_NAME)))
    return {'isolated_upgrade_database_created' if create else 'isolated_upgrade_database_removed':True}


def seed():
    with connect() as conn:
        assert conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0004_g4'
        conn.execute('INSERT INTO workspaces(id,name) VALUES(%s,%s),(%s,%s)',(WS,'G5 upgrade fixture',WS_OTHER,'Other fixture'))
        for user in (OWNER,MEMBER,FOREIGN,VIEWER,INACTIVE):
            conn.execute('INSERT INTO users(id,email,password_hash) VALUES(%s,%s,%s)',(user,str(user)+'@upgrade.invalid','!no-login'))
        for user,workspace,role,active in [(OWNER,WS,'owner',True),(MEMBER,WS,'member',True),
            (FOREIGN,WS_OTHER,'owner',True),(VIEWER,WS,'viewer',True),(INACTIVE,WS,'member',False)]:
            conn.execute('INSERT INTO memberships(workspace_id,user_id,role,active) VALUES(%s,%s,%s,%s)',(workspace,user,role,active))
        package,version=uuid4(),uuid4()
        conn.execute('INSERT INTO plugin_packages(id,workspace_id,name) VALUES(%s,%s,%s)',(package,WS,'upgrade-opc'))
        conn.execute('INSERT INTO plugin_versions(id,workspace_id,package_id,manifest_version,source_sha256) VALUES(%s,%s,%s,%s,%s)',
            (version,WS,package,'legacy-fixture','a'*64))
        conn.execute('INSERT INTO installations(workspace_id,package_id,plugin_version_id,enabled) VALUES(%s,%s,%s,true)',(WS,package,version))
        for skill in SKILLS.values():
            conn.execute('INSERT INTO skills(workspace_id,plugin_version_id,name,body) VALUES(%s,%s,%s,%s)',
                (WS,version,skill,'Pinned legacy fixture skill'))
        state={'workflow':'opc-v2','timezone':'Asia/Saigon','checkpoint':{'stage':STAGES[0],'status':'in_progress','unknown_extension':'retain'},
               'legacy_context':{'keep':True}}
        for project in (PROJECT,UNRESOLVED):
            conn.execute('INSERT INTO projects(id,workspace_id,plugin_version_id,name,revision,state) VALUES(%s,%s,%s,%s,4,%s::jsonb)',
                (project,WS,version,'Legacy project '+str(project),json.dumps(state)))
        old_commit=uuid4()
        conn.execute('INSERT INTO stage_commits(id,workspace_id,project_id,user_id,revision,idempotency_key,decision,assumptions) VALUES(%s,%s,%s,%s,1,%s,%s,%s::jsonb)',
            (old_commit,WS,PROJECT,OWNER,'legacy-key','Preserve prior decision',json.dumps([{'id':'old','status':'legacy-unverified'}])))
    db=Database()
    with db.tenant(Principal(OWNER,SCOPES),WS) as t:
        artifact=ArtifactStore(Path('/data'),t).put([b'Prior immutable artifact: exact bytes'],
            'text/plain',max_bytes=100,project_id=PROJECT)
    db.engine.dispose()
    MARKER.write_text(json.dumps({'version':str(version),'state':state,'commit_id':str(old_commit),
        'artifact_id':str(artifact.id),'artifact_sha256':artifact.sha256}),encoding='utf8')
    return {'seeded_revision':'0004_g4','legacy_projects':2,'legacy_artifact':True,'legacy_stage_commit':True}


def verify():
    marker=json.loads(MARKER.read_text(encoding='utf8'))
    db=Database(); principal=Principal(MEMBER,SCOPES)
    with connect() as conn:
        rows=conn.execute('SELECT id,lead_user_id,plugin_version_id,revision,state FROM projects WHERE workspace_id=%s ORDER BY id',(WS,)).fetchall()
        check('upgrade leaves unknown ownership unresolved, even with an owner and member',len(rows)==2 and all(row[1] is None for row in rows))
        check('upgrade preserves legacy pin revision and state',all(str(row[2])==marker['version'] and row[3]==4 and row[4]==marker['state'] for row in rows))
        check('operator can list projects needing explicit ownership confirmation',len(unassigned(conn,WS)['items'])==2)
    with db.tenant(principal,WS) as t:
        w=Workflows(t,Path('/data'))
        check('read reports unresolved lead',w.read_project(PROJECT)['lead_assignment_required'])
        try: w.project(PROJECT,write=True)
        except Conflict: blocked=True
        else: blocked=False
        check('no self-claim through project write',blocked)
    with connect() as conn:
        def rejected(name, lead=MEMBER, confirmed=OWNER, evidence='Verified owner confirmation fixture'):
            try:
                with conn.transaction(): assign(conn,WS,UNRESOLVED,lead,confirmed,evidence)
            except Exception as exc: check(name,getattr(exc,'sqlstate',None) in ('42501','22023'))
            else: raise AssertionError(name)
        rejected('missing proof rejected',evidence='')
        rejected('member cannot confirm ownership',confirmed=MEMBER)
        rejected('foreign workspace lead rejected',lead=FOREIGN)
        rejected('viewer lead rejected',lead=VIEWER)
        rejected('inactive membership lead rejected',lead=INACTIVE)
    proof='Fixture owner explicitly confirms member as lead; no inference from prior contributions'
    cli=['python','-m','goodmcp.project_admin','assign-lead','--workspace',str(WS),'--project',str(PROJECT),
         '--lead-user',str(MEMBER),'--confirmed-by',str(OWNER),'--evidence',proof]
    result=subprocess.run(cli,capture_output=True,text=True,check=True)
    assigned=json.loads(result.stdout)
    with connect() as conn:
        replay=assign(conn,WS,PROJECT,MEMBER,OWNER,proof)
        check('operator assignment retry is idempotent',str(replay['assignment_id'])==assigned['assignment_id'])
        row=conn.execute('SELECT lead_user_id,plugin_version_id,revision,state FROM projects WHERE id=%s',(PROJECT,)).fetchone()
        check('assignment changes only verified lead',row[0]==MEMBER and str(row[1])==marker['version'] and row[2]==4 and row[3]==marker['state'])
        check('ambiguous project remains unassigned',len(unassigned(conn,WS)['items'])==1)
        check('ownership proof and audit retained',conn.execute('SELECT evidence FROM project_lead_assignments WHERE project_id=%s',(PROJECT,)).fetchone()[0]==proof
              and conn.execute("SELECT count(*) FROM audit_events WHERE action='legacy_project_lead_assigned'").fetchone()[0]==1)
        for name,statement in [('lead remains immutable after recovery','UPDATE projects SET lead_user_id=%s WHERE id=%s'),
            ('unassigned project cannot bypass assignment','UPDATE projects SET lead_user_id=%s WHERE id=%s')]:
            project=PROJECT if 'after recovery' in name else UNRESOLVED
            try:
                with conn.transaction(): conn.execute(statement,(OWNER,project))
            except Exception as exc: check(name,getattr(exc,'sqlstate',None)=='42501')
            else: raise AssertionError(name)
    with db.engine.connect() as c:
        check('runtime cannot execute operator function',not c.execute(text(
            "SELECT has_function_privilege(current_user,'hub_assign_legacy_project_lead(uuid,uuid,uuid,uuid,text)','EXECUTE')")).scalar_one())
        check('ownership records hidden without tenant context',c.execute(text('SELECT count(*) FROM project_lead_assignments')).scalar_one()==0)
    with db.tenant(principal,WS) as t:
        w=Workflows(t,Path('/data'))
        check('prior artifact bytes and checksum survive actual migration',b''.join(w.store.stream(marker['artifact_id']))==b'Prior immutable artifact: exact bytes'
              and w.store.get(marker['artifact_id']).sha256==marker['artifact_sha256'])
        saved=w.save_artifact(PROJECT,{'expected_revision':4,'idempotency_key':'after-upgrade-save',
            'logical_path':'opc-doc/outputs/01-resource-audit/upgrade.md','content':'New output after verified ownership recovery'})
        committed=w.commit_stage(PROJECT,{'expected_revision':saved['revision'],'idempotency_key':'after-upgrade-commit','stage':STAGES[0],
            'action':'checkpoint','summary':'Resumed safely after upgrading old database'})
        check('verified lead can save and resume old project',committed['revision']==6 and committed['resume_stage']==STAGES[0])
        check('legacy context survives new commit',w.read_project(PROJECT)['checkpoint']['unknown_extension']=='retain')
    with connect() as conn:
        prior=conn.execute('SELECT decision,assumptions FROM stage_commits WHERE id=%s',(marker['commit_id'],)).fetchone()
        check('old decision and assumption history remain exact',prior==('Preserve prior decision',[{'id':'old','status':'legacy-unverified'}]))
    db.engine.dispose()
    return {'passed':True,'checks':checks,'upgrade_from':'0004_g4','ownership_auto_assigned':False}


if __name__=='__main__':
    if os.environ.get('HUB_ALLOW_TEST_FIXTURES')!='1': raise RuntimeError('Test fixtures disabled')
    operation=sys.argv[1]
    if operation in ('seed','check') and os.environ.get('HUB_DB_NAME')!=DB_NAME: raise RuntimeError('Isolated upgrade database required')
    result=database_operation(operation=='create') if operation in ('create','drop') else seed() if operation=='seed' else verify()
    print(json.dumps(result,ensure_ascii=True))
