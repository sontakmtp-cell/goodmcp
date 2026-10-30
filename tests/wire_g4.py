"""OAuth-backed, real HTTP/MCP jobs and constrained Python runner acceptance."""
import asyncio
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from wire_g3 import API,login,BASE

STATE=Path('/wirestate/g4.json');checks=[]


def numeric_value(value):
    if isinstance(value,float) and value.is_integer():return int(value)
    if isinstance(value,dict):return {k:numeric_value(v) for k,v in value.items()}
    if isinstance(value,list):return [numeric_value(v) for v in value]
    return value


def check(name,condition,**details):
    checks.append({'name':name,'passed':bool(condition),**details})
    if not condition:raise AssertionError(name)


def wait(api,job_id,timeout=120):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        job=api.data('GET','/jobs/'+job_id)
        if job['state'] in ('succeeded','failed','cancelled'):return job
        time.sleep(0.1)
    raise AssertionError('Job timeout in acceptance harness')


def submit(api,binding,arguments,key=None):
    return api.data('POST','/invocations',json={'binding_id':binding,'arguments':arguments,'idempotency_key':key or uuid4().hex})


def get_setup():
    g3=json.loads(Path('/wirestate/g3.json').read_text())
    installation=next(r['installation']['id'] for r in g3['records'] if r['directory']=='vietnam-finance-tax-expert')
    api=API(login('hub:read tools:run'))
    bindings={{'hub_search':'search','hub_read_chunk':'read_chunk'}.get(b['mcp_name'],b['mcp_name'].removeprefix('finance_')):b['id'] for b in api.data('GET',f'/installations/{installation}/bindings')}
    bindings['_probe']=bindings.pop('g4_test_probe')
    return api,installation,bindings


def full():
    api,installation,bindings=get_setup();fixtures=json.loads(Path('/app/tests/fixtures/g4/parity.json').read_text())
    baseline=json.loads(Path('/baseline/parity.json').read_text());expected={r['id']:r['result_sha256'] for r in baseline['cases']}
    check('operator approved 9 calculator/reference bindings',len(bindings)==10)
    readonly=API(login('hub:read'))
    r=readonly.request('POST','/invocations',json={'binding_id':bindings['cit_estimate'],'arguments':{'revenue':1,'cost':0},'idempotency_key':uuid4().hex})
    check('read-only OAuth cannot execute',r.status_code==403)
    check('invalid province rejected before queue',api.request('POST','/invocations',json={'binding_id':bindings['location_sim'],'arguments':{'headcount':1,'factory_area':1,'land_area':1,'provinces':['bad']},'idempotency_key':uuid4().hex}).status_code==422)
    check('invocation cannot select shell/image',api.request('POST','/invocations',json={'binding_id':bindings['cit_estimate'],'arguments':{'revenue':1,'cost':0},'idempotency_key':uuid4().hex,'image':'bad'}).status_code==422)
    timings=[];records=[]
    for case in fixtures['cases']:
        start=time.monotonic();job=submit(api,bindings[case['operation']],case['arguments']);accepted=time.monotonic()-start
        job=wait(api,job['id']);check('wire parity '+case['id'],job['state']=='succeeded')
        digest=hashlib.sha256(json.dumps(numeric_value(job['result']['data']),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        check('original value/hash '+case['id'],digest==expected[case['id']])
        timings.append(time.monotonic()-start);records.append({'id':case['id'],'job_id':job['id'],'acceptance_s':accepted,'end_to_end_s':timings[-1]})
    key=uuid4().hex;args={'revenue':100,'cost':10}
    a=submit(api,bindings['cit_estimate'],args,key);b=submit(api,bindings['cit_estimate'],args,key)
    check('same key/input reuses job',a['id']==b['id'])
    check('conflicting idempotency input returns 409',api.request('POST','/invocations',json={'binding_id':bindings['cit_estimate'],'arguments':{'revenue':101,'cost':10},'idempotency_key':key}).status_code==409)
    document_start=time.monotonic()
    documents=api.data('GET',f'/installations/{installation}/documents',params={'limit':100})
    check('documents list source handles',len(documents['items'])>0)
    matched=api.data('POST',f'/installations/{installation}/documents/search',json={'keywords':['thuế'],'limit':5})
    check('literal keyword lookup has no relevance scores',bool(matched['items']) and all('score' not in r for r in matched['items']))
    first=matched['items'][0]
    page=api.data('GET',f'/installations/{installation}/documents/{first["resource_id"]}',params={'length':16384})
    check('agent can follow keyword result to source text',bool(page['content']) and page['source_sha256']==first['source_sha256'])
    boundary=min(20,page['chars'])
    small=api.data('GET',f'/installations/{installation}/documents/{first["resource_id"]}',params={'length':boundary})
    continuation=api.data('GET',f'/installations/{installation}/documents/{first["resource_id"]}',params={'offset':boundary,'length':20})
    check('full text paging preserves source characters',small['content']+continuation['content']==page['content'][:boundary+20])
    literal=api.data('POST',f'/installations/{installation}/documents/search',json={'keywords':["'; DROP TABLE document_texts; --"],'limit':5})
    check('keywords treated as literal not SQL or wildcards',literal['items']==[])
    search_latency=time.monotonic()-document_start
    search=wait(api,a['id'])
    # The same token cannot select another workspace or reuse a foreign job/binding handle.
    foreign=api.client.get(BASE+'/api/v1/workspaces/20000000-0000-4000-8000-000000000002/jobs/'+search['id'],headers={'Authorization':'Bearer '+api.credentials['access_token']})
    check('cross workspace job handle denied',foreign.status_code==404)
    boundary=wait(api,submit(api,bindings['_probe'],{'kind':'boundaries'})['id'])
    check('runner has no secrets DB network socket or source writes',boundary['state']=='succeeded' and all(boundary['result']['data'].values()))
    crash=wait(api,submit(api,bindings['_probe'],{'kind':'crash'})['id'])
    check('nonzero process exit is failed not success',crash['state']=='failed' and crash['error']['code']=='tool_exit')
    asyncio.run(mcp_wire(api,installation))
    state={'credentials':api.credentials,'installation_id':installation,'bindings':bindings,'completed_job':search['id']}
    STATE.write_text(json.dumps(state))
    return {'passed':True,'checks':checks,'parity_cases':len(records),'parity':records,'calculator_end_to_end_median_s':statistics.median(timings),
            'document_lookup_and_read_s':search_latency,'source_tree_sha256':search['result']['provenance']['source_tree_sha256']}


async def mcp_wire(api,installation):
    refreshed=api.client.post('/auth/token',data={'grant_type':'refresh_token','client_id':api.credentials['client_id'],
        'refresh_token':api.credentials['refresh_token'],'resource':BASE+'/mcp'})
    assert refreshed.status_code==200;api.credentials.update(refreshed.json())
    async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+api.credentials['access_token']},timeout=20) as http:
        async with Client(streamable_http_client(BASE+'/mcp',http_client=http),mode='2026-07-28') as client:
            tools=await client.list_tools();known={t.name:t for t in tools.tools}
            check('MCP declares typed Python input and job poll',{'finance_cit_estimate','hub_run_tool','hub_get_job','hub_cancel_job','hub_search','hub_list_documents','hub_read_document'}<=known.keys() and known['finance_cit_estimate'].input_schema.get('properties',{}).get('arguments') is not None)
            listing=await client.call_tool('hub_list_documents',{'installation_id':installation,'limit':5})
            check('MCP document listing is readonly',not listing.is_error and known['hub_list_documents'].annotations.read_only_hint)
            found=await client.call_tool('hub_search',{'installation_id':installation,'keywords':['thuế'],'limit':3})
            check('MCP agent can choose literal keywords',not found.is_error and bool(found.structured_content['items']) and known['hub_search'].annotations.read_only_hint)
            resource=found.structured_content['items'][0]
            content=await client.call_tool('hub_read_document',{'installation_id':installation,'resource_id':resource['resource_id'],'length':2048})
            check('MCP agent follows result to actual document',not content.is_error and bool(content.structured_content['content']) and content.structured_content['source_sha256']==resource['source_sha256'])
            start=time.monotonic()
            result=await client.call_tool('finance_cit_estimate',{'installation_id':installation,'arguments':{'revenue':1000,'cost':100},'idempotency_key':uuid4().hex})
            check('MCP accepts job within sync budget',not result.is_error and time.monotonic()-start<10)
            job=wait(api,result.structured_content['job']['id'])
            check('MCP original Python result',job['state']=='succeeded' and job['result']['data']['cit_with_incentive_VND']==180)
            result=await client.call_tool('hub_get_job',{'job_id':job['id']})
            check('MCP polls durable typed result',not result.is_error and result.structured_content['job']['state']=='succeeded')
            result=await client.call_tool('finance_tariff',{'installation_id':installation,'arguments':{'cif':0,'category':'vehicle'},'idempotency_key':uuid4().hex})
            check('MCP rejects invalid financial input',result.is_error)


def faults():
    state=json.loads(STATE.read_text());api=API(state['credentials']);bindings=state['bindings']
    first=submit(api,bindings['_probe'],{'kind':'sleep'});second=submit(api,bindings['_probe'],{'kind':'sleep'})
    for _ in range(100):
        jobs=[api.data('GET','/jobs/'+j['id']) for j in (first,second)]
        if all(j['state']=='running' for j in jobs):break
        time.sleep(0.1)
    check('two light jobs can run concurrently',all(j['state']=='running' for j in jobs))
    queued=submit(api,bindings['cit_estimate'],{'revenue':100,'cost':0})
    check('third light job stays queued',queued['state']=='queued')
    result=api.data('POST','/jobs/'+queued['id']+'/cancel')
    check('queued cancel is terminal',result['state']=='cancelled')
    start=time.monotonic()
    docs=api.data('POST',f'/installations/{state["installation_id"]}/documents/search',json={'keywords':['thuế'],'limit':5})
    check('document lookup remains responsive with two Python jobs',bool(docs['items']) and time.monotonic()-start<10)
    for job in (first,second):api.data('POST','/jobs/'+job['id']+'/cancel')
    for job in (first,second):check('running job stops before cancelled',wait(api,job['id'])['state']=='cancelled')
    timeout=wait(api,submit(api,bindings['_probe'],{'kind':'sleep'})['id'],60)
    check('execution timeout is failed and bounded',timeout['state']=='failed' and timeout['error']['code']=='timeout')
    check('completed result immutable on late cancel',api.data('POST','/jobs/'+state['completed_job']+'/cancel')['state']=='succeeded')
    recovery=submit(api,bindings['_probe'],{'kind':'sleep'})
    for _ in range(100):
        job=api.data('GET','/jobs/'+recovery['id'])
        if job['state']=='running':break
        time.sleep(0.1)
    state.update(credentials=api.credentials,recovery_job=recovery['id']);STATE.write_text(json.dumps(state))
    return {'passed':True,'checks':checks,'recovery_job_running':job['state']=='running'}


def recovered():
    state=json.loads(STATE.read_text());api=API(state['credentials']);start=time.monotonic()
    while time.monotonic()-start<70:
        job=api.data('GET','/jobs/'+state['recovery_job'])
        if job['state']=='running' and job['attempts']>=2:break
        time.sleep(0.2)
    check('dispatcher crash resumes only after lease with new attempt',job['state']=='running' and job['attempts']==2)
    api.data('POST','/jobs/'+job['id']+'/cancel');job=wait(api,job['id'])
    check('crashed attempt never reported success',job['state']=='cancelled' and job['result_artifact_id'] is None)
    state['credentials']=api.credentials;STATE.write_text(json.dumps(state))
    return {'passed':True,'checks':checks}


def resume():
    state=json.loads(STATE.read_text());api=API(state['credentials']);job=api.data('GET','/jobs/'+state['completed_job'])
    check('job result artifact survives all-container recreation',job['state']=='succeeded' and 'cit_with_incentive_VND' in job['result']['data'])
    return {'passed':True,'checks':checks}


def quotas():
    state=json.loads(STATE.read_text());api=API(state['credentials']);binding=state['bindings']['cit_estimate']
    jobs=[submit(api,binding,{'revenue':100,'cost':10}) for _ in range(20)]
    check('twenty queued jobs admitted',all(j['state']=='queued' for j in jobs))
    extra=api.request('POST','/invocations',json={'binding_id':binding,'arguments':{'revenue':100,'cost':10},'idempotency_key':uuid4().hex})
    check('queue limit returns 429 with retry after',extra.status_code==429 and extra.headers.get('retry-after')=='3')
    for job in jobs:assert api.data('POST','/jobs/'+job['id']+'/cancel')['state']=='cancelled'
    check('queued quota fixtures cancelled without execution',True)
    state['credentials']=api.credentials;STATE.write_text(json.dumps(state))
    return {'passed':True,'checks':checks}


if __name__=='__main__':print(json.dumps({'full':full,'faults':faults,'recovered':recovered,'resume':resume,'quotas':quotas}[sys.argv[1]](),ensure_ascii=False))
