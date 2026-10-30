import json
import math
import struct
import pytest
from pydantic import ValidationError
from goodmcp.finance_spec import validate, MODELS
from goodmcp.docker_engine import demux


@pytest.mark.parametrize('operation,args',[
 ('cit_estimate',{'revenue':-1,'cost':0}),('cit_estimate',{'revenue':float('nan'),'cost':0}),
 ('cit_estimate',{'revenue':float('inf'),'cost':0}),('cit_estimate',{'revenue':1,'cost':0,'year':0}),
 ('cit_schedule',{'revenue':1,'cost':0,'horizon':100000000}),('payroll_total',{'headcount':1.2,'monthly_gross_wage':1}),
 ('payroll_total',{'headcount':-1,'monthly_gross_wage':1}),('fct_withhold',{'gross_payment':1,'rate':-100}),
 ('fct_grossup',{'net_amount':1,'rate':101}),('tariff',{'cif':0,'category':'vehicle'}),
 ('tariff',{'cif':1,'category':'unknown'}),('location_sim',{'headcount':1,'factory_area':1,'land_area':1,'provinces':['wrong']}),
 ('refs_odi',{'shell':'rm -rf /'}),('cit_estimate',{'revenue':1,'cost':0,'image':'unapproved'}),
 ('location_sim',{'headcount':1,'factory_area':-1,'land_area':1})])
def test_runtime_bounds(operation,args):
    with pytest.raises(ValidationError):validate(operation,args)


def test_zero_override_preserved_and_province_never_silently_dropped():
    assert validate('location_sim',{'headcount':0,'factory_area':0,'land_area':0,'cit_override':0})['cit_override']==0
    assert validate('tariff',{'cif':1,'category':'vehicle','vat_override':0})['vat_override']==0


def test_engine_stream_multiplex_and_truncation():
    raw=b'\x01\0\0\0'+struct.pack('>I',3)+b'out'+b'\x02\0\0\0'+struct.pack('>I',3)+b'err'
    assert demux(raw)==(b'out',b'err')
    with pytest.raises(RuntimeError):demux(raw[:-1])


def test_all_business_schemas_reject_extra_fields():
    for m in MODELS.values():assert m.model_json_schema()['additionalProperties'] is False
