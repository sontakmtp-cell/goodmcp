"""Thin calls to original, hash-verified Python. No reproduced formulas."""
import contextlib
import io
import json
from common import load, PLUGIN
from finance_spec import validate


def run(operation, arguments):
    args=validate(operation,arguments)
    warnings=['Matches supplied Python; not a legal/tax audit. Source dates may be outdated.']
    if operation in ('cit_estimate','cit_schedule','payroll_total','fct_withhold','fct_grossup'):
        data=getattr(load('calculators'),operation)(**args)
    elif operation=='tariff': data=load('tariff').calc(**args)
    elif operation=='location_sim':
        load('calculators')
        if args['provinces'] is not None: args['provinces']=','.join(args['provinces'])
        data=load('location_sim').simulate(**args)
        if args['cit_override']==0: warnings.append('Original location_sim ignores cit_override=0 when profit is provided; preserved, not corrected.')
    elif operation in ('refs_calendar','refs_odi'):
        m=load('refs'); out=io.StringIO()
        with contextlib.redirect_stdout(out): getattr(m,'show_calendar' if operation=='refs_calendar' else 'show_odi')()
        filename='compliance_calendar.json' if operation=='refs_calendar' else 'odi_checklist.json'
        data={'text':out.getvalue(),'source':json.loads((PLUGIN/'references/data'/filename).read_text())}
    else: raise ValueError('Unsupported light adapter')
    return {'data':data,'warnings':warnings}
