import hashlib
import importlib.util
import json
from pathlib import Path
import sys

PLUGIN = Path('/plugin')
APP = Path('/runtime')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()


def load(name):
    approved=json.loads((APP/'reviewed-source.json').read_text())
    p=PLUGIN/approved[name]['path']
    if sha(p)!=approved[name]['sha256']:raise ValueError('Reviewed code checksum mismatch')
    spec=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m


def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
