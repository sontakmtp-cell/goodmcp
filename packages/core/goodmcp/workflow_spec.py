"""OPC file/transition contract v2. Pure validation, no model execution."""
import re
import unicodedata
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

STAGES = ('01-resource-audit','02-niche-positioning','03-value-proposition','04-business-model',
          '05-mvp-design','06-conversion-loop','execution','07-asset-ops','08-dashboard-review')
SKILLS = dict(zip(STAGES, ('opc-resource-audit','opc-niche-positioning','opc-value-proposition',
    'opc-business-model-design','opc-mvp-designer','opc-conversion-loop','opc-orchestrator','opc-asset-ops','opc-dashboard-review')))
LEGACY = {'06-mvp-design':'05-mvp-design','06-mvp':'05-mvp-design','07-conversion-loop':'06-conversion-loop',
          '08-asset-ops':'07-asset-ops','09-dashboard-review':'08-dashboard-review'}
STATE_PATH = 'opc-doc/state/current-stage.json'
SUMMARY_PATH = 'opc-doc/outputs/00-orchestrator/session-summary.md'
Key = Annotated[str, Field(min_length=1,max_length=100)]
Revision = Annotated[int, Field(ge=0,strict=True)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OpenProject(Strict):
    installation_id: UUID
    name: str = Field(min_length=1,max_length=200)
    idempotency_key: Key
    timezone: str = Field(default='Asia/Saigon',min_length=1,max_length=100)


class SaveArtifact(Strict):
    expected_revision: Revision
    idempotency_key: Key
    logical_path: str = Field(min_length=1,max_length=240)
    content: str = Field(max_length=262144)
    media_type: Literal['text/markdown','text/plain','application/json'] = 'text/markdown'


class Decision(Strict):
    id: Key
    stage: str = Field(min_length=1,max_length=64)
    decision: str = Field(min_length=1,max_length=4000)
    evidence: list[str] = Field(default_factory=list,max_length=20)
    authorization: str = Field(min_length=1,max_length=2000)


class Assumption(Strict):
    id: Key
    statement: str = Field(min_length=1,max_length=4000)
    status: Literal['unverified','supported','rejected','inconclusive'] = 'unverified'
    evidence: list[str] = Field(default_factory=list,max_length=20)


class Review(Strict):
    id: Key
    review: str = Field(min_length=1,max_length=4000)
    evidence: list[str] = Field(default_factory=list,max_length=20)


class Skip(Strict):
    stage: str
    reason: str = Field(min_length=1,max_length=2000)
    authorization: str = Field(min_length=1,max_length=2000)
    missing_evidence: str = Field(min_length=1,max_length=2000)


class CommitStage(Strict):
    expected_revision: Revision
    idempotency_key: Key
    stage: str = Field(min_length=1,max_length=64)
    action: Literal['complete','skip','rollback','checkpoint'] = 'complete'
    next_stage: str | None = Field(default=None,max_length=64)
    artifact_ids: list[UUID] = Field(default_factory=list,max_length=30)
    decisions: list[Decision] = Field(default_factory=list,max_length=30)
    assumptions: list[Assumption] = Field(default_factory=list,max_length=30)
    reviews: list[Review] = Field(default_factory=list,max_length=20)
    skipped_stages: list[Skip] = Field(default_factory=list,max_length=8)
    summary: str = Field(min_length=1,max_length=8000)
    authorization: str = Field(default='',max_length=4000)
    open_questions: list[str] = Field(default_factory=list,max_length=30)
    checkpoint_extra: dict = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)


class HostReport(Strict):
    name: str = Field(min_length=1,max_length=100)
    file_access: bool = False
    tools: bool = True
    subagents: bool = False
    model_selection: bool = False
    available_models: list[Annotated[str,Field(min_length=1,max_length=200)]] = Field(default_factory=list,max_length=100)
    requested_model: str | None = Field(default=None,max_length=200)
    reported_model: str | None = Field(default=None,max_length=200)
    evidence: str = Field(default='unknown',min_length=1,max_length=2000)


def canonical_stage(stage):
    stage = LEGACY.get(stage, stage)
    if stage not in STAGES: raise ValueError('Ambiguous or unknown stage; use full semantic stage ID')
    return stage


def checkpoint(value):
    if not isinstance(value,dict): raise ValueError('Malformed checkpoint; preserve original bytes')
    if not value.get('stage'): raise ValueError('Checkpoint needs a semantic stage ID')
    result = dict(value)
    for key in ('stage','next_stage'):
        if result.get(key): result[key] = canonical_stage(result[key])
    if result.get('status') not in ('draft','in_progress','completed'): raise ValueError('Malformed checkpoint status')
    if result['status']=='completed' and not result.get('next_stage'): raise ValueError('Completed checkpoint needs next_stage')
    for key in ('skipped_stages','stale_outputs'):
        if key in result:
            if not isinstance(result[key],list): raise ValueError('Malformed checkpoint history')
            result[key] = [canonical_stage(x) if isinstance(x,str) else {**x,'stage':canonical_stage(x['stage'])} for x in result[key]]
    return result


def resume_stage(value):
    c = checkpoint(value)
    return c['next_stage'] if c['status']=='completed' else c['stage']


def logical_path(value):
    if (not isinstance(value,str) or len(value)>240 or unicodedata.normalize('NFC',value)!=value
        or not value.startswith('opc-doc/') or not re.fullmatch(r'[\w./-]+',value)):
        raise ValueError('Invalid logical path')
    if any(p in ('','.','..') or p.endswith('.') for p in value.split('/')): raise ValueError('Invalid logical path')
    return value


def history_append(value, records, key):
    """Extend known legacy containers without flattening unknown keys or overwriting IDs."""
    if isinstance(value,list): items=value; result=list(value); target=result
    elif isinstance(value,dict):
        candidates=[k for k in (key,'records','items') if isinstance(value.get(k),list)]
        if len(candidates)!=1: raise ValueError('Ambiguous legacy history container; preserve original')
        items=value[candidates[0]]; result={**value,candidates[0]:list(items)}; target=result[candidates[0]]
    else: raise ValueError('Malformed history; preserve original')
    seen={x['id']:x for x in items if isinstance(x,dict) and 'id' in x}
    for record in records:
        if record['id'] in seen:
            # Timestamps of existing identical business records are retained.
            old={k:v for k,v in seen[record['id']].items() if k not in ('recorded_at','updated_at')}
            new={k:v for k,v in record.items() if k not in ('recorded_at','updated_at')}
            if old!=new: raise ValueError('History ID conflicts; append a new record ID')
        else: target.append(record); seen[record['id']]=record
    return result
