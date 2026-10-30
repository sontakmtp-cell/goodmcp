"""Independent direct-original parity and frozen retrieval benchmark; no model API."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import resource
import statistics
import sys
import time
from adapter import run
from common import load, PLUGIN, canonical, sha


def numeric_value(value):
    # JSON number 20 and 20.0 represent the same original Python value.
    if isinstance(value,float) and value.is_integer():return int(value)
    if isinstance(value,dict):return {k:numeric_value(v) for k,v in value.items()}
    if isinstance(value,list):return [numeric_value(v) for v in value]
    return value


def parity():
    fixtures=json.loads(Path('/fixtures/parity.json').read_text());results=[]
    calculators=load('calculators');tariff=load('tariff');location=load('location_sim');refs=load('refs')
    for case in fixtures['cases']:
        op,args=case['operation'],dict(case['arguments']);start=time.monotonic()
        if op in ('cit_estimate','cit_schedule','payroll_total','fct_withhold','fct_grossup'):expected=getattr(calculators,op)(**args)
        elif op=='tariff':expected=tariff.calc(**args)
        elif op=='location_sim':
            if args.get('provinces') is not None:args['provinces']=','.join(args['provinces'])
            expected=location.simulate(**args)
        else:
            output=io.StringIO()
            with contextlib.redirect_stdout(output):getattr(refs,'show_calendar' if op=='refs_calendar' else 'show_odi')()
            name='compliance_calendar.json' if op=='refs_calendar' else 'odi_checklist.json'
            expected={'text':output.getvalue(),'source':json.loads((PLUGIN/'references/data'/name).read_text())}
        actual=run(op,case['arguments']);assert actual['data']==expected,case['id']
        # Independent small golden values catch unintended formula/rounding changes.
        if op=='cit_estimate' and case['arguments'].get('year') in (1,4,5,13,14):
            assert actual['data']['cit_with_incentive_VND']=={1:0,4:0,5:600000000,13:600000000,14:1200000000}[case['arguments']['year']]
        if op=='payroll_total' and args['monthly_gross_wage']==11000000:assert actual['data']['pit_per_head_monthly_VND']==0
        json.loads(canonical(actual))
        results.append({'id':case['id'],'operation':op,'passed':True,'elapsed_s':time.monotonic()-start,'result_sha256':hashlib.sha256(canonical(numeric_value(actual['data'])).encode()).hexdigest()})
    return {'passed':True,'cases':results,'count':len(results),'fixture_sha256':sha('/fixtures/parity.json'),
        'peak_rss_MiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}



if __name__=='__main__':
    result=parity()
    Path('/evidence/parity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(canonical({k:v for k,v in result.items() if k!='cases'}))
