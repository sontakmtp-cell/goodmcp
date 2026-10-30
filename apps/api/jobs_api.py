from contextlib import contextmanager
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from apps.api.registry_api import authorized
from goodmcp.jobs import Jobs
from goodmcp.finance_spec import MODELS


class Invocation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    binding_id:UUID
    arguments:dict
    idempotency_key:str=Field(min_length=1,max_length=100)
    project_id:UUID|None=None


@contextmanager
def jobs_for(database,token,workspace):
    with authorized(database,token,workspace) as r:yield Jobs(r.t,r.store.root)


def routes(database):
    r=APIRouter(prefix='/api/v1/workspaces/{workspace_id}')
    def envelope(request,data):return {'data':data,'request_id':request.state.request_id}

    @r.get('/installations/{installation_id}/bindings')
    def bindings(workspace_id:UUID,installation_id:UUID,request:Request):
        with jobs_for(database,request.state.access_token,workspace_id) as j:return envelope(request,j.bindings(installation_id))

    @r.post('/invocations',status_code=202)
    def invoke(workspace_id:UUID,payload:Invocation,request:Request):
        with jobs_for(database,request.state.access_token,workspace_id) as j:
            return envelope(request,j.enqueue(payload.binding_id,payload.arguments,payload.idempotency_key,payload.project_id))

    @r.get('/jobs/{job_id}')
    def get(workspace_id:UUID,job_id:UUID,request:Request):
        with jobs_for(database,request.state.access_token,workspace_id) as j:return envelope(request,j.get_job(job_id))

    @r.post('/jobs/{job_id}/cancel')
    def cancel(workspace_id:UUID,job_id:UUID,request:Request):
        with jobs_for(database,request.state.access_token,workspace_id) as j:return envelope(request,j.cancel_job(job_id))
    return r


def tools(mcp,database):
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.types import ToolAnnotations
    from goodmcp.database import NotFound, Forbidden
    from goodmcp.storage import Conflict

    class JobResult(BaseModel):
        job:dict

    def call(method,*args):
        token=get_access_token()
        if token is None:raise ValueError('Authentication required')
        try:
            with jobs_for(database,token,token.claims['workspace_id']) as j:return JobResult(job=getattr(j,method)(*args))
        except (NotFound,Forbidden,Conflict,ValueError) as exc:raise ValueError(str(exc)) from None
        except Exception:raise ValueError('Runtime unavailable') from None

    write=ToolAnnotations(read_only_hint=False,destructive_hint=False,idempotent_hint=True,open_world_hint=False)
    read=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)

    @mcp.tool(annotations=write)
    def hub_run_tool(binding_id:UUID,arguments:dict,idempotency_key:Annotated[str,Field(min_length=1,max_length=100)],project_id:UUID|None=None)->JobResult:
        """Queue an approved Python binding; requires tools:run. Returns job handle immediately. Same key/input reuses job; commands/images/paths are forbidden."""
        return call('enqueue',binding_id,arguments,idempotency_key,project_id)

    @mcp.tool(annotations=read)
    def hub_get_job(job_id:UUID)->JobResult:
        """Read this workspace's job state, errors and durable result. No worker leases or private paths."""
        return call('get_job',job_id)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False,destructive_hint=True,idempotent_hint=True,open_world_hint=False))
    def hub_cancel_job(job_id:UUID)->JobResult:
        """Request cancellation. Running jobs become cancelled only after the isolated container/process stops. Requires tools:run."""
        return call('cancel_job',job_id)

    descriptions={
      'cit_estimate':'Original Python CIT estimate including tax holiday year and loss carry.',
      'cit_schedule':'Original Python annual CIT holiday/reduction schedule, up to 100 years.',
      'payroll_total':'Original Python payroll and estimated PIT calculation in VND, original rounding.',
      'fct_withhold':'Original Python FCT withholding from gross payment.',
      'fct_grossup':'Original Python FCT gross-up from net payment.',
      'tariff':'Original indicative import duty/SCT/VAT calculation. Positive CIF; real rates need HS classification.',
      'location_sim':'Original province cost comparison. Original cit_override=0 behavior is preserved and warned.',
      'refs_calendar':'Original Python compliance calendar text and supplied JSON; source dates may be outdated.',
      'refs_odi':'Original Python ODI checklist text and supplied JSON. No external actions.'}

    def register(operation,model):
        # Evaluated model annotation supplies a distinct JSON schema for each operation.
        def invoke(installation_id:UUID,arguments:model,idempotency_key:Annotated[str,Field(min_length=1,max_length=100)])->JobResult:
            token=get_access_token()
            if token is None:raise ValueError('Authentication required')
            try:
                with jobs_for(database,token,token.claims['workspace_id']) as j:
                    binding=j.operation_binding(installation_id,operation)
                    return JobResult(job=j.enqueue(binding,arguments.model_dump(),idempotency_key))
            except (NotFound,Forbidden,Conflict,ValueError) as exc:raise ValueError(str(exc)) from None
            except Exception:raise ValueError('Runtime unavailable') from None
        name='finance_'+operation
        mcp.tool(name=name,description='Queue and poll hub_get_job. Requires tools:run. '+descriptions[operation]+' Supplied Python parity is not a legal/tax audit.',annotations=write)(invoke)
    for operation,model in MODELS.items():register(operation,model)
