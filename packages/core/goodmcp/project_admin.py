"""Operator-only lead recovery. Never exposed through REST/MCP or runtime credentials."""
import argparse
import json
from uuid import UUID
from .admin import connect


def unassigned(conn, workspace_id):
    rows=conn.execute('''SELECT id,name,plugin_version_id,revision,created_at FROM projects
        WHERE workspace_id=%s AND lead_user_id IS NULL ORDER BY id''',(workspace_id,)).fetchall()
    return {'items':[dict(zip(('id','name','plugin_version_id','revision','created_at'),row)) for row in rows]}


def assign(conn, workspace_id, project_id, lead_user_id, confirmed_by, evidence):
    # All IDs and the owner-confirmation evidence are explicit operator inputs.
    assignment_id=conn.execute('SELECT hub_assign_legacy_project_lead(%s,%s,%s,%s,%s)',
        (workspace_id,project_id,lead_user_id,confirmed_by,evidence)).fetchone()[0]
    return {'project_id':project_id,'lead_user_id':lead_user_id,'assignment_id':assignment_id}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    listing=sub.add_parser('list-unassigned'); listing.add_argument('--workspace',type=UUID,required=True)
    assignment=sub.add_parser('assign-lead')
    for name in ('workspace','project','lead-user','confirmed-by'):
        assignment.add_argument('--'+name,type=UUID,required=True)
    assignment.add_argument('--evidence',required=True,help='Reference to verified owner confirmation; never infer ownership from contributions')
    args=parser.parse_args()
    try:
        with connect() as conn:
            result=unassigned(conn,args.workspace) if args.operation=='list-unassigned' else assign(conn,
                args.workspace,args.project,args.lead_user,args.confirmed_by,args.evidence)
        print(json.dumps(result,default=str,ensure_ascii=True))
    except Exception:
        print(json.dumps({'error':'lead_assignment_rejected','message':'Check project, active membership and explicit owner-confirmation evidence'}))
        raise SystemExit(1)


if __name__=='__main__': main()
