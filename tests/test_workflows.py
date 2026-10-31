"""G5 acceptance against real PostgreSQL RLS and immutable filesystem blobs."""
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from goodmcp.database import Database, Principal, NotFound, Forbidden
from goodmcp.fixtures import USER_A, USER_B, VIEWER, WORKSPACE_A, WORKSPACE_B
from goodmcp.storage import Conflict
from goodmcp.workflows import Workflows
from goodmcp.workflow_spec import STAGES, SKILLS, STATE_PATH, SUMMARY_PATH, checkpoint, canonical_stage, history_append
from test_registry import zipped, publish

SCOPES=frozenset({'hub:read','hub:write','projects:read','projects:write','tools:run'})
LEAD=Principal(USER_A,SCOPES)
PATH='opc-doc/outputs/01-resource-audit/report.md'


def opc_zip(version='1.0.0'):
    roster=[{'role':'role-'+str(i),'skill':skill,'preferred_model':'selector-sol','reasoning_effort':'high'}
            for i,skill in enumerate(dict.fromkeys(SKILLS.values()))]
    files={'plugin.json':json.dumps({'name':'g5-opc-'+uuid4().hex,'version':version,'license':'MIT'}),
        'skills/opc-orchestrator/references/team-roster.json':json.dumps(roster)}
    for skill in SKILLS.values(): files['skills/'+skill+'/SKILL.md']='---\nname: '+skill+'\ndescription: Fixture only\n---\nPinned role '+version
    return zipped(files)


@pytest.fixture
def project(db,storage_root):
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); v=publish(w,opc_zip()); install=w.set_installation(v,True,0)
        p=w.open_project({'installation_id':str(install['id']),'name':'G5 project','idempotency_key':uuid4().hex})
    return p,install


def save(w,p,revision=0,key=None,content='# Report\nConfirmed context; evidence still unknown.',path=PATH):
    return w.save_artifact(p['id'],{'expected_revision':revision,'idempotency_key':key or uuid4().hex,
        'logical_path':path,'content':content})


def commit(w,p,revision,artifacts=None,**changes):
    return w.commit_stage(p['id'],{'expected_revision':revision,'idempotency_key':uuid4().hex,
        'stage':STAGES[0],'summary':'User accepted resource inventory; assumptions remain unverified',
        'authorization':'User confirmed inventory in conversation','artifact_ids':artifacts or [],**changes})


def test_draft_resume_complete_and_replay(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); s=save(w,p,key='draft-key'); assert save(w,p,key='draft-key')==s
        assert w.read_project(p['id'])['resume_stage']==STAGES[0]
        request={'expected_revision':1,'idempotency_key':'complete-key','stage':STAGES[0],
            'artifact_ids':[s['file']['artifact_id']],'summary':'Accepted','authorization':'Confirmed by user',
            'assumptions':[{'id':'market','statement':'Unproven demand','status':'unverified','evidence':[]}],
            'checkpoint_extra':{'unknown_extension':{'keep':True}}}
        c=w.commit_stage(p['id'],request)
        assert w.commit_stage(p['id'],request)==c
        assert c['resume_stage']==STAGES[1] and c['revision']==2
        history=w.file_history(p['id'],PATH)['items']; assert len(history)==2
        assert [f['status'] for f in history]==['draft','confirmed']
        assert w.read_file(p['id'],history[0]['id'])['content'].startswith('# Report')
        assert w._json(p['id'],'opc-doc/state/assumptions.json',[]) [0]['status']=='unverified'
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); resumed=w.prepare_workflow(p['id'])
        assert resumed['stage']==STAGES[1] and resumed['plugin_version_id']==p['plugin_version_id']
        assert resumed['checkpoint']['unknown_extension']=={'keep':True}


def test_revision_and_idempotency_conflicts_leave_history(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t: save(Workflows(t,storage_root),p,key='same')
    for revision,key,content in [(0,'new','stale'),(1,'same','changed')]:
        with pytest.raises(Conflict):
            with db.tenant(LEAD,WORKSPACE_A) as t: save(Workflows(t,storage_root),p,revision,key,content)
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); assert w.read_project(p['id'])['revision']==1
        assert len(w.file_history(p['id'],PATH)['items'])==1


def test_real_concurrent_writers_one_wins(db,storage_root,project):
    p,_=project; concurrent=Database(pool_size=2)
    def writer(content):
        try:
            with concurrent.tenant(LEAD,WORKSPACE_A) as t:
                return save(Workflows(t,storage_root),p,content=content)['revision']
        except Conflict: return 'conflict'
    try:
        with ThreadPoolExecutor(2) as executor: results=list(executor.map(writer,['Writer A','Writer B']))
        assert sorted(map(str,results))==['1','conflict']
    finally: concurrent.engine.dispose()


def test_atomic_failed_checkpoint_and_retry(db,storage_root,project,monkeypatch):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t: s=save(Workflows(t,storage_root),p)
    original=Workflows._state_file
    def fail(self,project,path,value,revision):
        if path==STATE_PATH: raise OSError('simulated checkpoint publication failure')
        return original(self,project,path,value,revision)
    with monkeypatch.context() as m:
        m.setattr(Workflows,'_state_file',fail)
        with pytest.raises(OSError):
            with db.tenant(LEAD,WORKSPACE_A) as t:
                commit(Workflows(t,storage_root),p,1,[s['file']['artifact_id']],
                       decisions=[{'id':'d','stage':STAGES[0],'decision':'keep','authorization':'user agreed'}])
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        assert w.read_project(p['id'])['revision']==1
        assert w._latest(p['id'],SUMMARY_PATH) is None
        assert w._latest(p['id'],'opc-doc/state/decisions.json') is None
        assert len(w.file_history(p['id'],PATH)['items'])==1
        assert commit(w,p,1,[s['file']['artifact_id']])['revision']==2


@pytest.mark.parametrize('scope', ['hub:read','hub:read hub:write','hub:read projects:read'])
def test_scope_required(db,storage_root,project,scope):
    p,_=project
    with db.tenant(Principal(USER_A,frozenset(scope.split())),WORKSPACE_A) as t:
        with pytest.raises(Forbidden): save(Workflows(t,storage_root),p)


def test_tenant_viewer_and_forged_lead(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t: s=save(Workflows(t,storage_root),p)
    with db.tenant(Principal(USER_B,SCOPES),WORKSPACE_B) as t:
        w=Workflows(t,storage_root)
        for action in [lambda:w.read_project(p['id']),lambda:w.read_file(p['id'],s['file']['id']),
                       lambda:w.prepare_workflow(p['id']),lambda:save(w,p),lambda:commit(w,p,1)]:
            with pytest.raises(NotFound): action()
        for table in ('project_files','project_operations','stage_commits'):
            assert t.connection.execute(text('SELECT count(*) FROM '+table+' WHERE project_id=:p'),{'p':p['id']}).scalar_one()==0
    with db.tenant(Principal(VIEWER,SCOPES),WORKSPACE_A) as t:
        w=Workflows(t,storage_root); assert w.read_project(p['id'])['id']==UUID(p['id'])
        with pytest.raises(Forbidden): save(w,p,1)
    with pytest.raises(ValueError):
        with db.tenant(LEAD,WORKSPACE_A) as t:
            Workflows(t,storage_root).save_artifact(p['id'],{'expected_revision':1,'idempotency_key':'fake','logical_path':PATH,'content':'bad','role':'lead'})


@pytest.mark.parametrize('path',['../../bad','opc-doc/state/current-stage.json',SUMMARY_PATH,'opc-doc/outputs/02-niche-positioning/future.md','opc-doc/outputs/01-resource-audit/../bad','C:/temp/file'])
def test_paths_and_stage_output_scope(db,storage_root,project,path):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        with pytest.raises((ValueError,Forbidden)): save(Workflows(t,storage_root),p,path=path)


def test_history_preserves_unknown_legacy_shapes():
    old={'schema':'legacy','decisions':[{'id':'one','decision':'old'}],'extra':{'keep':1}}
    new=history_append(old,[{'id':'two','decision':'new'}],'decisions')
    assert new['extra']==old['extra'] and len(new['decisions'])==2 and len(old['decisions'])==1
    with pytest.raises(ValueError): history_append(old,[{'id':'one','decision':'overwritten'}],'decisions')
    with pytest.raises(ValueError): history_append({'unknown':[]},[],'decisions')


@pytest.mark.parametrize('old,new',[('06-mvp-design','05-mvp-design'),('06-mvp','05-mvp-design'),('07-conversion-loop','06-conversion-loop'),('08-asset-ops','07-asset-ops'),('09-dashboard-review','08-dashboard-review')])
def test_legacy_semantic_ids(old,new):
    assert canonical_stage(old)==new
    assert checkpoint({'stage':old,'status':'draft','custom':1})['custom']==1
    with pytest.raises(ValueError): canonical_stage('06')


def test_legacy_checkpoint_normalization_and_unknown_keys(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); row=w.project(p['id'])
        legacy={'stage':'06-mvp-design','status':'draft','custom':{'retained':1},'stale_outputs':['07-conversion-loop']}
        w._state_file(row,STATE_PATH,legacy,0)
        assert w.prepare_workflow(p['id'])['stage']=='05-mvp-design'
        result=commit(w,p,0,stage='05-mvp-design',action='checkpoint',authorization='',checkpoint_extra={'another':True})
        assert result['checkpoint']['custom']==legacy['custom'] and result['checkpoint']['numbering_version']==2
        assert result['checkpoint']['stale_outputs']==['06-conversion-loop']
        assert len(w.file_history(p['id'],STATE_PATH)['items'])==3


def test_malformed_json_is_preserved(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); row=w.project(p['id'])
        bad=w._file(row,STATE_PATH,'{ broken JSON','text/plain',0,'state')
    with pytest.raises(Conflict):
        with db.tenant(LEAD,WORKSPACE_A) as t: commit(Workflows(t,storage_root),p,0,action='checkpoint')
    with db.tenant(LEAD,WORKSPACE_A) as t:
        assert Workflows(t,storage_root).read_file(p['id'],bad['id'])['content']=='{ broken JSON'


def test_conflicting_legacy_outputs_surface_without_overwrite(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); row=w.project(p['id'])
        old=w._file(row,'opc-doc/outputs/06-mvp-design/plan.md','Historical confirmed result','text/markdown',0,'confirmed')
        new=w._file(row,'opc-doc/outputs/05-mvp-design/plan.md','Canonical conflicting result','text/markdown',0,'confirmed')
        assert len(w.read_project(p['id'])['legacy_conflicts'])==1
        with pytest.raises(Conflict): commit(w,p,0,action='checkpoint')
        assert w.read_file(p['id'],old['id'])['content']=='Historical confirmed result'
        assert w.read_file(p['id'],new['id'])['content']=='Canonical conflicting result'


def test_structured_histories_merge_and_record_ids_conflict(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); row=w.project(p['id'])
        w._state_file(row,'opc-doc/state/decisions.json',{'schema':'legacy','decisions':[{'id':'old','decision':'keep'}],'extra':42},0)
        d={'id':'new','stage':STAGES[0],'decision':'Accepted unknown','authorization':'Already confirmed'}
        commit(w,p,0,action='checkpoint',decisions=[d])
        value=w._json(p['id'],'opc-doc/state/decisions.json',{})
        assert value['extra']==42 and len(value['decisions'])==2
        commit(w,p,1,action='checkpoint',decisions=[d])
        assert len(w._json(p['id'],'opc-doc/state/decisions.json',{})['decisions'])==2
        with pytest.raises(Conflict): commit(w,p,2,action='checkpoint',decisions=[{**d,'decision':'Overwrite old result'}])


def test_skip_rollback_stale_and_conditional_routing(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        with pytest.raises(ValueError): commit(w,p,0,action='skip',next_stage=STAGES[2])
        c=commit(w,p,0,action='skip',next_stage=STAGES[2],skipped_stages=[
            {'stage':s,'reason':'Known context','authorization':'User explicitly requested skip','missing_evidence':'No source document'} for s in STAGES[:2]])
        assert c['resume_stage']==STAGES[2] and len(c['checkpoint']['skipped_stages'])==2
        r=commit(w,p,1,stage=STAGES[2],action='rollback',next_stage=STAGES[0])
        assert r['resume_stage']==STAGES[0] and STAGES[2] in r['checkpoint']['stale_outputs']
        # Returning to execution/07/08 is explicit; no implicit conditional phase completion.
        w._state_file(w.project(p['id']),STATE_PATH,{'stage':'06-conversion-loop','status':'draft'},2)
        s=save(w,p,2,path='opc-doc/outputs/06-conversion-loop/first-message.md')
        r=commit(w,p,3,[s['file']['artifact_id']],stage='06-conversion-loop')
        assert r['resume_stage']=='execution'
        assert w.prepare_workflow(p['id'])['stage']=='execution'


def test_host_modes_models_and_pin_upgrade(db,storage_root,project):
    p,i=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        brief=w.prepare_workflow(p['id']); assert brief['execution_mode']=='single_assistant_sequential'
        assert brief['reported_model']=='unknown' and not brief['server_invokes_models']
        profile=w.report_host({'name':'Test host','subagents':True,'model_selection':True,'available_models':['selector-sol'],
            'requested_model':'selector-sol','reported_model':'host-model','evidence':'Test fixture report, no inference'})
        b=w.prepare_workflow(p['id'],profile['id'])
        assert b['requested_model']=='selector-sol' and b['reported_model']=='host-model'
        assert b['execution_mode']=='native_delegation_available' and b['execution_status']=='not_started'
        assert b['specialist_write_scope']==[]
        w.set_installation(p['plugin_version_id'],False,1)
        with pytest.raises(NotFound): w.prepare_workflow(p['id'])
        # User project data stays readable when a plugin is disabled.
        assert w.read_project(p['id'])['revision']==0
        w.set_installation(p['plugin_version_id'],True,2)


def test_repeated_outputs_need_timestamps_and_counters(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        w._state_file(w.project(p['id']),STATE_PATH,{'stage':'07-asset-ops','status':'in_progress'},0)
        with pytest.raises(ValueError): save(w,p,path='opc-doc/outputs/07-asset-ops/old-name.md')
        first=save(w,p,path='opc-doc/outputs/07-asset-ops/20261031-080000.md')
        with pytest.raises(Conflict): save(w,p,1,path='opc-doc/outputs/07-asset-ops/20261031-080000.md')
        with pytest.raises(ValueError): commit(w,p,1,[first['file']['artifact_id']],stage='07-asset-ops')
        result=commit(w,p,1,[first['file']['artifact_id']],stage='07-asset-ops',next_stage='execution')
        assert result['resume_stage']=='execution'


def test_project_file_composite_fk_cannot_attach_other_project_blob(db,storage_root,project):
    p,_=project
    with pytest.raises(DBAPIError) as error:
        with db.tenant(LEAD,WORKSPACE_A) as t:
            w=Workflows(t,storage_root)
            other=w.store.put([b'not owned by project'],'text/plain',max_bytes=100)
            w._link(w.project(p['id']),PATH,other.id,0,'draft')
    assert error.value.orig.sqlstate=='23503'


def test_foreign_project_artifact_cannot_complete_stage(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); foreign=w.store.put([b'foreign'],'text/plain',max_bytes=100)
        with pytest.raises(NotFound): commit(w,p,0,[str(foreign.id)])


def test_draft_checkpoint_does_not_confirm_assumptions(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        result=commit(w,p,0,action='checkpoint',authorization='',assumptions=[{'id':'a','statement':'No experiment yet'}])
        assert result['resume_stage']==STAGES[0] and result['checkpoint']['status']=='draft'
        with pytest.raises(ValueError): commit(w,p,1,action='checkpoint',assumptions=[{'id':'b','statement':'Not measured','status':'supported'}])


def test_immutable_database_history_and_pin(db,storage_root,project):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t: save(Workflows(t,storage_root),p)
    for sql in ["UPDATE project_files SET status='confirmed' WHERE project_id=:p",
                "DELETE FROM project_operations WHERE project_id=:p",
                "UPDATE projects SET plugin_version_id=NULL WHERE id=:p"]:
        with pytest.raises(DBAPIError):
            with db.tenant(LEAD,WORKSPACE_A) as t: t.connection.execute(text(sql),{'p':p['id']})


def test_fourth_document_plugin_project(db,storage_root):
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); name='docs-'+uuid4().hex
        v=publish(w,zipped({'plugin.json':json.dumps({'name':name,'version':'1','license':'MIT'})}))
        i=w.set_installation(v,True,0)
        p=w.open_project({'installation_id':str(i['id']),'name':'Custom plugin','idempotency_key':uuid4().hex})
        assert p['workflow']=='documents-v1'
        s=save(w,p,path='opc-doc/outputs/custom/code.txt',content='print("saved, never executed")')
        assert w.read_file(p['id'],s['file']['id'])['content']=='print("saved, never executed")'
        with pytest.raises(ValueError): w.prepare_workflow(p['id'])


def test_pinned_required_outputs_and_scorecard_schema(db,storage_root):
    from io import BytesIO
    import zipfile
    raw=opc_zip(); buffer=BytesIO()
    with zipfile.ZipFile(BytesIO(raw)) as src, zipfile.ZipFile(buffer,'w') as dst:
        for path in src.namelist():
            body=src.read(path)
            if path=='skills/opc-resource-audit/SKILL.md':
                body+='\n## Đầu ra và hoàn thành\n- `inventory.md`: resources\n- `scorecard.json`: structured\n'.encode()
            dst.writestr(path,body)
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); v=publish(w,buffer.getvalue()); i=w.set_installation(v,True,0)
        p=w.open_project({'installation_id':str(i['id']),'name':'Output validation','idempotency_key':uuid4().hex})
        assert w.prepare_workflow(p['id'])['required_outputs']==['inventory.md','scorecard.json']
        first=save(w,p,path='opc-doc/outputs/01-resource-audit/inventory.md')
        with pytest.raises(ValueError,match='Missing required'): commit(w,p,1,[first['file']['artifact_id']])
        invalid=save(w,p,1,path='opc-doc/outputs/01-resource-audit/scorecard.json',content='[]')
        with pytest.raises(ValueError,match='eight resource'): commit(w,p,2,[first['file']['artifact_id'],invalid['file']['artifact_id']])
        value=[{'category':'category-'+str(n),'items':[],'availability':'unknown','activation_cost':'unknown','unknowns':[],'confirmed':True} for n in range(8)]
        valid=save(w,p,2,path='opc-doc/outputs/01-resource-audit/scorecard.json',content=json.dumps(value))
        result=commit(w,p,3,[first['file']['artifact_id'],valid['file']['artifact_id']])
        assert result['resume_stage']==STAGES[1]


@pytest.mark.parametrize('current,destination',[(STAGES[0],STAGES[1]),(STAGES[0],STAGES[-1]),
    ('05-mvp-design','execution'),('execution','07-asset-ops'),('07-asset-ops','08-dashboard-review'),
    ('08-dashboard-review','08-dashboard-review')])
def test_review_rollback_cannot_advance_or_stay(db,storage_root,project,current,destination):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        w._state_file(w.project(p['id']),STATE_PATH,{'stage':current,'status':'in_progress','custom':'preserve'},0)
    with pytest.raises(ValueError,match='Rollback'):
        with db.tenant(LEAD,WORKSPACE_A) as t:
            commit(Workflows(t,storage_root),p,0,stage=current,action='rollback',next_stage=destination)
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); state=w.read_project(p['id'])
        assert state['resume_stage']==current and state['revision']==0
        assert state['checkpoint']['custom']=='preserve'
        assert t.connection.execute(text('SELECT count(*) FROM stage_commits WHERE project_id=:p'),{'p':p['id']}).scalar_one()==0


def test_review_many_commits_rotate_summary_without_losing_history(db,storage_root,project):
    p,_=project; entries=[]; first_file=None
    for n in range(75):
        content=f'REVIEW_ENTRY_{n:03d}\n'+('x'*7900 if n%2 else 'Việt🙂'*1500)
        entries.append(content)
        payload={'expected_revision':n,'idempotency_key':f'review-summary-{n}', 'stage':STAGES[0],
            'action':'checkpoint','summary':content}
        with db.tenant(LEAD,WORKSPACE_A) as t:
            w=Workflows(t,storage_root); result=w.commit_stage(p['id'],payload)
            if n==0: first_file=w._latest(p['id'],SUMMARY_PATH)['id']
            if n in (30,60): assert w.commit_stage(p['id'],payload)==result
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); state=w.read_project(p['id'],limit=100)
        assert state['revision']==75 and state['resume_stage']==STAGES[0]
        segments=sorted((f for f in state['files'] if '/session-summary-segments/' in f['logical_path']),key=lambda f:f['logical_path'])
        assert len(segments)>=2
        active=w._latest(p['id'],SUMMARY_PATH)
        ids=[f['artifact_id'] for f in segments]+[active['artifact_id']]
        parts=[b''.join(w.store.stream(artifact)) for artifact in ids]
        assert all(len(part)<=262144 for part in parts)
        history=''.join(part.decode('utf8') for part in parts)
        for n,content in enumerate(entries):
            assert history.count(f'REVIEW_ENTRY_{n:03d}\n')==1 and content in history
        assert w.read_file(p['id'],first_file)['content'].endswith(entries[0])
        assert len(w.file_history(p['id'],SUMMARY_PATH,limit=100)['items'])==75


@pytest.mark.parametrize('current,destination',[('02-niche-positioning',STAGES[0]),('execution','06-conversion-loop'),
    ('07-asset-ops','execution'),('08-dashboard-review','07-asset-ops')])
def test_review_rollback_to_earlier_stage_preserves_context(db,storage_root,project,current,destination):
    p,_=project
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root)
        w._state_file(w.project(p['id']),STATE_PATH,{'stage':current,'status':'in_progress','extension':42},0)
        result=commit(w,p,0,stage=current,action='rollback',next_stage=destination)
        assert result['resume_stage']==destination and result['checkpoint']['extension']==42
        assert len(w.file_history(p['id'],STATE_PATH)['items'])==3


def test_review_summary_rotation_preserves_legacy_bytes_and_rolls_back_atomically(db,storage_root,project,monkeypatch):
    p,_=project; legacy='Prior legacy summary\n'+'x'*252000
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); old=w._file(w.project(p['id']),SUMMARY_PATH,legacy,'text/markdown',0,'state')
    original=Workflows._state_file
    def fail(self,project,path,value,revision):
        if path==STATE_PATH: raise OSError('checkpoint failure after summary rotation')
        return original(self,project,path,value,revision)
    request={'expected_revision':0,'idempotency_key':'rotate-retry','stage':STAGES[0],'action':'checkpoint','summary':'Việt🙂'*1500}
    with monkeypatch.context() as m:
        m.setattr(Workflows,'_state_file',fail)
        with pytest.raises(OSError):
            with db.tenant(LEAD,WORKSPACE_A) as t: Workflows(t,storage_root).commit_stage(p['id'],request)
    with db.tenant(LEAD,WORKSPACE_A) as t:
        w=Workflows(t,storage_root); state=w.read_project(p['id'])
        assert state['revision']==0 and not any('/session-summary-segments/' in f['logical_path'] for f in state['files'])
        assert w._latest(p['id'],SUMMARY_PATH)['id']==old['id']
        assert b''.join(w.store.stream(old['artifact_id'])).decode()==legacy
        result=w.commit_stage(p['id'],request); assert w.commit_stage(p['id'],request)==result
        segments=[f for f in w.read_project(p['id'])['files'] if '/session-summary-segments/' in f['logical_path']]
        assert len(segments)==1 and segments[0]['artifact_id']==old['artifact_id']
        assert b''.join(w.store.stream(segments[0]['artifact_id'])).decode()==legacy
        assert w.read_file(p['id'],old['id'])['sha256']==w.store.get(old['artifact_id']).sha256
