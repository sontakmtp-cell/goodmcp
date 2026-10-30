"""Operator-only approval: match baked reviewed release to immutable G3 registry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID
from .admin import connect
from .finance_spec import MODELS


def approve(conn,release,workspace,version,probes=False):
    if release.get('mode')!='python-calculators-keyword-mvp':raise ValueError('TF-IDF releases are not MVP runtimes')
    row=conn.execute('SELECT source_sha256,metadata FROM plugin_versions WHERE workspace_id=%s AND id=%s',(workspace,version)).fetchone()
    if row is None or row[0]!=release['source_zip_sha256'] or row[1]['tree_sha256']!=release['source_tree_sha256']:raise ValueError('Registry source differs from approved build')
    files=dict(conn.execute('SELECT logical_path,metadata->>\'sha256\' FROM resources WHERE workspace_id=%s AND plugin_version_id=%s',(workspace,version)).fetchall())
    if any(files.get(p)!=h for p,h in release['registry_files'].items()):raise ValueError('Registry file hash mismatch')
    digest=hashlib.sha256(json.dumps(release['manifest'],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if digest!=release['release_digest']:raise ValueError('Release manifest hash mismatch')
    conn.execute('''INSERT INTO runtime_releases(workspace_id,plugin_version_id,image_digest,release_digest,source_tree_sha256,manifest)
      VALUES(%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(workspace_id,plugin_version_id) DO NOTHING''',
      (workspace,version,release['image_digest'],release['release_digest'],release['source_tree_sha256'],json.dumps(release['manifest'])))
    existing=conn.execute('SELECT image_digest,release_digest FROM runtime_releases WHERE workspace_id=%s AND plugin_version_id=%s',(workspace,version)).fetchone()
    if existing!=(release['image_digest'],release['release_digest']):raise ValueError('Immutable release already approved with a different image')
    bindings=[]
    for op in (*MODELS,*(['_probe'] if probes else [])):
        schema=MODELS[op].model_json_schema() if op in MODELS else {'type':'object','properties':{'kind':{'enum':['sleep','crash','boundaries']}},'required':['kind'],'additionalProperties':False}
        limits={'class':'light','timeout_s':30,'memory_MiB':256}
        name='g4_test_probe' if op=='_probe' else 'finance_'+op
        row=conn.execute('''INSERT INTO tool_bindings(workspace_id,plugin_version_id,mcp_name,adapter_id,image_digest,input_schema,output_schema,limits)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb) ON CONFLICT(workspace_id,plugin_version_id,mcp_name) DO NOTHING RETURNING id''',
          (workspace,version,name,op,release['image_digest'],json.dumps(schema),json.dumps({'type':'object'}),json.dumps(limits))).fetchone()
        bindings.append(op)
    return {'approved':True,'version_id':str(version),'bindings':bindings,'image_digest':release['image_digest'],'release_digest':release['release_digest']}


def backfill_documents(conn):
    from .database import Database,Principal
    from .documents import project_document
    from .storage import ArtifactStore
    database=Database();counts={'versions':0,'resources':0}
    rows=conn.execute("""SELECT DISTINCT i.workspace_id,i.plugin_version_id,m.user_id FROM installations i JOIN LATERAL
      (SELECT user_id FROM memberships WHERE workspace_id=i.workspace_id AND active AND role IN ('owner','admin') ORDER BY created_at LIMIT 1) m ON true
      WHERE i.enabled""").fetchall()
    for workspace,version,user in rows:
        with database.tenant(Principal(user,frozenset({'hub:read','hub:write'})),workspace) as t:
            store=ArtifactStore(Path('/data'),t)
            resources=t.connection.execute(__import__('sqlalchemy').text('SELECT id,logical_path,metadata,artifact_id FROM resources WHERE plugin_version_id=:v'),{'v':version}).mappings().all()
            for r in resources:project_document(t,store,r['id'],r['logical_path'],r['metadata'],r['artifact_id'])
            counts['resources']+=len(resources);counts['versions']+=1
    database.engine.dispose();return counts


def main():
    p=argparse.ArgumentParser();p.add_argument('--release',type=Path,default=Path('/release/release.json'));p.add_argument('--workspace',type=UUID);p.add_argument('--version',type=UUID);p.add_argument('--active',action='store_true');p.add_argument('--test-probes',action='store_true')
    a=p.parse_args()
    if a.test_probes and os.environ.get('HUB_ALLOW_TEST_FIXTURES')!='1':raise ValueError('Test bindings disabled')
    release=json.loads(a.release.read_text())
    with connect() as conn:
        if a.active:
            rows=conn.execute('''SELECT v.workspace_id,v.id FROM plugin_versions v JOIN installations i
              ON i.workspace_id=v.workspace_id AND i.plugin_version_id=v.id AND i.enabled WHERE v.source_sha256=%s''',(release['source_zip_sha256'],)).fetchall()
            if not rows:raise ValueError('Import and enable the approved source version first')
            result={'approved_versions':[approve(conn,release,*row,a.test_probes) for row in rows]}
        else:
            if not a.workspace or not a.version:raise ValueError('Use --active or both --workspace and --version')
            result=approve(conn,release,a.workspace,a.version,a.test_probes)
        result['document_projection']=backfill_documents(conn)
    print(json.dumps(result))


if __name__=='__main__':main()
