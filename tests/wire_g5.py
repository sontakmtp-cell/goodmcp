"""G5: fresh OAuth chats, real HTTP + MCP, restart, pinned versions. No LLM calls."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys
from uuid import uuid4
import zipfile

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from wire_g3 import API, login, BASE
from wire_g4 import wait

STATE=Path('/wirestate/g5.json')
SCOPES='hub:read hub:write projects:read projects:write tools:run'
checks=[]


def check(name,condition,**details):
    checks.append({'name':name,'passed':bool(condition),**details})
    if not condition: raise AssertionError(name)


def full():
    api=API(login(SCOPES))
    g3=json.loads(Path('/wirestate/g3.json').read_text())
    opc=next(x for x in g3['records'] if x['directory']=='OPC Team')
    path='opc-doc/outputs/01-resource-audit/inventory.md'
    create={'installation_id':opc['installation']['id'],'name':'G5 cross-chat OPC','idempotency_key':uuid4().hex}
    project=api.data('POST','/projects',json=create); pid=project['id']
    check('create retry returns same pinned project',api.data('POST','/projects',json=create)==project)
    check('open pins original OPC version',project['plugin_version_id']==opc['version_id'])
    check('project discoverable across chats',any(x['id']==pid for x in api.data('GET','/projects')['items']))
    brief=api.data('GET',f'/projects/{pid}/workflow')
    check('real OPC nine roles retained',len(brief['team_roster'])==9)
    check('no host subagents means honest sequential mode',brief['execution_mode']=='single_assistant_sequential'
        and brief['reported_model']=='unknown' and not brief['server_invokes_models'] and brief['execution_status']=='not_started')
    save={'expected_revision':0,'idempotency_key':uuid4().hex,'logical_path':path,
          'content':'# Resource inventory\n\nUser context: local fixture.\nUnknowns: market demand unverified.'}
    draft=api.data('POST',f'/projects/{pid}/artifacts',json=save)
    check('draft save retry does not duplicate',api.data('POST',f'/projects/{pid}/artifacts',json=save)==draft)
    check('draft does not advance',api.data('GET',f'/projects/{pid}')['resume_stage']=='01-resource-audit')
    check('unknown lead claim rejected',api.request('POST',f'/projects/{pid}/artifacts',json={**save,'role':'lead'}).status_code==422)
    check('stale save rejected',api.request('POST',f'/projects/{pid}/artifacts',json={**save,'idempotency_key':uuid4().hex}).status_code==409)
    check('idempotency input conflict rejected',api.request('POST',f'/projects/{pid}/artifacts',json={**save,'content':'changed'}).status_code==409)
    readonly=API(login('hub:read projects:read'))
    check('project reader cannot write',readonly.request('POST',f'/projects/{pid}/artifacts',json=save).status_code==403)
    hubonly=API(login('hub:read hub:write'))
    check('hub scopes do not imply project access',hubonly.request('GET',f'/projects/{pid}').status_code==403)
    response=api.client.get(BASE+'/api/v1/workspaces/20000000-0000-4000-8000-000000000002/projects/'+pid,
        headers={'Authorization':'Bearer '+api.credentials['access_token']})
    check('grant cannot choose foreign workspace project',response.status_code==404)
    categories=['Kinh nghiệm','Hiểu nhóm người','Năng lực','Quan hệ','Kênh','Tài sản','Ràng buộc','Giới hạn cứng']
    scorecard=[{'category':category,'items':[],'availability':'unknown accepted in fixture',
        'activation_cost':'unknown','unknowns':['Fixture; no business claim'],'confirmed':True} for category in categories]
    structured=api.data('POST',f'/projects/{pid}/artifacts',json={'expected_revision':1,'idempotency_key':uuid4().hex,
        'logical_path':'opc-doc/outputs/01-resource-audit/scorecard.json','content':json.dumps(scorecard,ensure_ascii=False),'media_type':'application/json'})
    commit={'expected_revision':2,'idempotency_key':uuid4().hex,'stage':'01-resource-audit',
        'artifact_ids':[draft['file']['artifact_id'],structured['file']['artifact_id']],'summary':'Inventory accepted; hypothesis still unverified',
        'authorization':'Fixture user explicitly accepts inventory',
        'decisions':[{'id':'inventory-accepted','stage':'01-resource-audit','decision':'Proceed with existing resources','authorization':'User accepted fixture inventory','evidence':['conversation fixture']}],
        'assumptions':[{'id':'demand','statement':'Market demand unknown','status':'unverified','evidence':[]}],
        'checkpoint_extra':{'custom_context':{'keep':'across chats'}}}
    done=api.data('POST',f'/projects/{pid}/stage-commits',json=commit)
    check('commit retries return stable result',api.data('POST',f'/projects/{pid}/stage-commits',json=commit)==done)
    check('confirmed stage resumes next stage',done['resume_stage']=='02-niche-positioning' and done['revision']==3)
    check('stale commit does not erase history',api.request('POST',f'/projects/{pid}/stage-commits',json={**commit,'idempotency_key':uuid4().hex}).status_code==409)
    history=api.data('GET',f'/projects/{pid}/file-history',params={'path':path})['items']
    check('draft and confirmed revisions preserved',len(history)==2 and history[-1]['status']=='confirmed')
    confirmed=api.data('GET',f'/projects/{pid}/files/{history[-1]["id"]}')
    check('historical artifact checksum and content available',confirmed['content']==save['content'] and len(confirmed['sha256'])==64)
    # Real concurrent HTTP writes, each holding the same optimistic revision.
    def write(content):
        return api.request('POST',f'/projects/{pid}/artifacts',json={'expected_revision':3,'idempotency_key':uuid4().hex,
            'logical_path':'opc-doc/outputs/02-niche-positioning/draft.md','content':content}).status_code
    with ThreadPoolExecutor(2) as executor: results=list(executor.map(write,['Concurrent writer A','Concurrent writer B']))
    check('concurrent HTTP writers preserve winner',sorted(results)==[200,409])
    # A new OAuth chat reads the same durable state via official MCP SDK.
    fresh=API(login(SCOPES))
    asyncio.run(mcp_chat(fresh,pid,opc['version_id']))
    # Installing a different source revision must not silently repin existing projects.
    source=Path('/samples/OPC Team.zip')
    buffer=io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(buffer,'w') as revised:
        for name in original.namelist():
            raw=original.read(name)
            if name.endswith('plugin.json'):
                manifest=json.loads(raw)
                if 'version' in manifest: manifest['version']='1.1.3-g5-fixture'
                raw=json.dumps(manifest,ensure_ascii=False).encode()
            revised.writestr(name,raw)
    imported=api.upload(raw=buffer.getvalue()); check('test update imported without executing code',imported['state']=='ready')
    updated=api.data('PUT','/installation',json={'version_id':imported['plugin_version_id'],'enabled':True,'expected_revision':opc['installation']['revision']})
    old_brief=api.data('GET',f'/projects/{pid}/workflow')
    check('installation update leaves project pinned to original source',old_brief['plugin_version_id']==opc['version_id'] and old_brief['stage']=='02-niche-positioning')
    resource=old_brief['contract_resources'][0]
    page=api.data('GET',f'/projects/{pid}/resources/{resource["id"]}',params={'length':128})
    check('pinned source handles remain readable after update',page['source_sha256']==resource['sha256'] and len(base64.b64decode(page['content']))<=128)
    # Restore the acceptance fixture installation so G3 resume remains independent.
    api.data('PUT','/installation',json={'version_id':opc['version_id'],'enabled':True,'expected_revision':updated['revision']})
    finance=next(x for x in g3['records'] if x['directory']=='vietnam-finance-tax-expert')
    fp=api.data('POST','/projects',json={'installation_id':finance['installation']['id'],'name':'G5 Python output pin','idempotency_key':uuid4().hex})
    binding=next(x for x in api.data('GET',f'/installations/{finance["installation"]["id"]}/bindings') if x['mcp_name']=='finance_cit_estimate')
    invocation={'binding_id':binding['id'],'arguments':{'revenue':1000000,'cost':100000},'project_id':fp['id'],'idempotency_key':uuid4().hex}
    job=wait(api,api.data('POST','/invocations',json=invocation)['id'])
    check('G4 Python job writes durable result to correctly pinned project',job['state']=='succeeded' and bool(job['result_artifact_id']))
    check('G4 Python binding rejects different project pin',api.request('POST','/invocations',json={**invocation,'project_id':pid,'idempotency_key':uuid4().hex}).status_code==409)
    STATE.write_text(json.dumps({'project_id':pid,'version_id':opc['version_id'],'revision':4,'confirmed_file_id':history[-1]['id'],
        'content':save['content'],'sha256':confirmed['sha256'],'finance_project_id':fp['id'],'job_id':job['id']}))
    return {'project_id':pid,'plugin_version_id':opc['version_id'],'final_revision':4,'llm_api_calls':0,'host_gate':'protocol_only'}


async def mcp_chat(api,pid,version):
    async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+api.credentials['access_token']}) as http:
        async with Client(streamable_http_client(BASE+'/mcp',http_client=http),mode='2026-07-28') as client:
                tools=await client.list_tools()
                known={x.name:x for x in tools.tools}
                check('G5 typed workflow tools exposed',{'hub_open_project','hub_read_project','hub_prepare_workflow',
                    'hub_save_artifact','hub_commit_stage','hub_read_project_file'}<=known.keys())
                async def call(name,args):
                    r=await client.call_tool(name,args)
                    check('MCP '+name,not r.is_error)
                    return r.structured_content['data']
                listing=await call('hub_list_projects',{})
                check('new MCP chat discovers existing project',any(x['id']==pid for x in listing['items']))
                p=await call('hub_read_project',{'project_id':pid})
                check('new chat resumes exact stage and pin',p['resume_stage']=='02-niche-positioning' and p['plugin_version_id']==version and p['revision']==4)
                report=await call('hub_report_host',{'payload':{'name':'SDK fixture','subagents':False,'reported_model':None,'evidence':'Protocol test; no model inference'}})
                brief=await call('hub_prepare_workflow',{'project_id':pid,'host_profile_id':report['id']})
                check('MCP brief honestly reports unknown actual model',brief['reported_model']=='unknown' and brief['execution_mode']=='single_assistant_sequential')
                native=await call('hub_report_host',{'payload':{'name':'Capability fixture','subagents':True,'model_selection':True,'available_models':['gpt-6.1-sol'],'reported_model':'caller-model','evidence':'Self report only'}})
                brief=await call('hub_prepare_workflow',{'project_id':pid,'host_profile_id':native['id']})
                check('native mode is availability only, never execution claim',brief['requested_model']=='gpt-6.1-sol' and brief['execution_status']=='not_started' and brief['model_evidence_source']=='caller_reported_not_verified')
                foreign=await client.call_tool('hub_read_project',{'project_id':str(uuid4())})
                check('MCP unknown project is_error',foreign.is_error)
                invalid=await client.call_tool('hub_save_artifact',{'project_id':pid,'payload':{'expected_revision':0,'idempotency_key':uuid4().hex,
                    'logical_path':'opc-doc/outputs/02-niche-positioning/conflict.md','content':'stale'}})
                check('MCP revision conflict is_error',invalid.is_error)


def resume():
    state=json.loads(STATE.read_text()); api=API(login(SCOPES)); pid=state['project_id']
    p=api.data('GET',f'/projects/{pid}')
    check('fresh OAuth after full recreation resumes stage pin revision',p['resume_stage']=='02-niche-positioning'
        and p['plugin_version_id']==state['version_id'] and p['revision']==state['revision'])
    check('checkpoint unknown extension survives recreate',p['checkpoint']['custom_context']=={'keep':'across chats'})
    page=api.data('GET',f'/projects/{pid}/files/{state["confirmed_file_id"]}')
    check('confirmed file and hash survive recreate',page['content']==state['content'] and page['sha256']==state['sha256'])
    check('project Python result survives recreate',api.data('GET','/jobs/'+state['job_id'])['state']=='succeeded')
    asyncio.run(mcp_chat(api,pid,state['version_id']))
    return {'project_id':pid,'resume_stage':p['resume_stage'],'revision':p['revision'],'new_oauth_grant':True,'llm_api_calls':0}


if __name__=='__main__':
    result=full() if sys.argv[1]=='full' else resume()
    print(json.dumps({'passed':True,'checks':checks,**result},ensure_ascii=False))
