"""Build a locked light Python calculator image from reviewed original files.

No corpus, TF-IDF, pickle or model is built/copied into the MVP runtime image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/core'))
from goodmcp.plugin_scan import tree_hash


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1048576):h.update(b)
    return h.hexdigest()


def prepare(source_root,code_root,destination):
    destination=destination.resolve();destination.mkdir(parents=True,exist_ok=False)
    context=destination/'context';(context/'runtime').mkdir(parents=True)
    baseline=json.loads((code_root/'Docs/reports/evidence/G0/inventory-before.json').read_text(encoding='utf8'))
    package=next(p for p in baseline['packages'] if p['directory']=='vietnam-finance-tax-expert')
    folder=source_root/'plugin_example'/package['directory'];files={}
    for p in folder.rglob('*'):
        if p.is_symlink():raise ValueError('Symlink source')
        if p.is_file():files[p.relative_to(folder).as_posix()]={'sha256':digest(p),'bytes':p.stat().st_size}
    assert files=={f['path']:{k:f[k] for k in ('sha256','bytes')} for f in package['files']},'Original source changed'
    approved=json.loads((code_root/'poc/g0/reviewed-source.json').read_text(encoding='utf8'))
    approved={k:v for k,v in approved.items() if k in ('calculators','location_sim','tariff','refs')}
    selected={v['path'] for v in approved.values()}
    selected.update(p for p in files if p.startswith('references/data/') and p.endswith('.json'))
    for p in selected:
        target=context/'source'/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(folder/p,target)
    for name in ('common.py','main.py'):
        shutil.copyfile(code_root/'runners/finance'/name,context/'runtime'/name)
    shutil.copyfile(code_root/'packages/plugin-adapters/finance/adapter.py',context/'runtime/adapter.py')
    shutil.copyfile(code_root/'packages/core/goodmcp/finance_spec.py',context/'runtime/finance_spec.py')
    (context/'runtime/reviewed-source.json').write_text(json.dumps(approved),encoding='utf8')
    for name in ('pyproject.toml','uv.lock'):shutil.copyfile(code_root/name,context/name)
    shutil.copyfile(code_root/'runners/finance/Dockerfile',context/'Dockerfile')
    identity=json.loads((code_root/'Docs/reports/evidence/G3/source-identity.json').read_text(encoding='utf8'))
    original=next(p for p in identity['packages'] if p['directory']==package['directory'])
    assert tree_hash(files)==original['tree_sha256']
    manifest={'mode':'python-calculators-keyword-mvp','source_tree_sha256':tree_hash(files),'source_zip_sha256':original['zip_sha256'],
      'registry_files':{p:files[p]['sha256'] for p in sorted(selected)},'lock_sha256':digest(context/'uv.lock'),
      'runtime_files':{p.name:digest(p) for p in (context/'runtime').iterdir()}}
    (context/'runtime/release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf8')
    tag='goodmcp-finance:'+destination.name.lower()
    subprocess.run(['docker','build','-t',tag,str(context)],check=True)
    image=subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip()
    release={'mode':manifest['mode'],'image_digest':image,'release_digest':digest(context/'runtime/release-manifest.json'),
      'source_tree_sha256':manifest['source_tree_sha256'],'source_zip_sha256':manifest['source_zip_sha256'],
      'registry_files':manifest['registry_files'],'manifest':manifest}
    (destination/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding='utf8')
    return destination/'release.json'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,default=ROOT);p.add_argument('--output',type=Path)
    a=p.parse_args();output=a.output or ROOT/'.local/g4'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    print(json.dumps({'release_file':str(prepare(a.source_root,ROOT,output))}))
