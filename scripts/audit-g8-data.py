"""Read-only operator audit on the VPS; emits hashes/fixture metadata, no secrets."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--compose', required=True, type=Path)
p.add_argument('--volume', required=True)
p.add_argument('--output', required=True, type=Path)
a = p.parse_args()

def output(args):
    return subprocess.check_output(args, text=True)

def query(sql):
    raw = output([str(a.compose.resolve()), 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'goodmcp', '-Atc', sql])
    return json.loads(raw)

root = Path(output(['docker', 'volume', 'inspect', a.volume, '--format', '{{.Mountpoint}}']).strip()).resolve(strict=True)
rows = query("SELECT coalesce(json_agg(x),'[]') FROM (SELECT id,storage_key,sha256,bytes FROM artifacts ORDER BY id) x")
failures = []
total = 0
for row in rows:
    file = root / row['storage_key']
    try:
        assert file.resolve(strict=True).is_relative_to(root) and not file.is_symlink()
        h = hashlib.sha256()
        with file.open('rb') as f:
            while block := f.read(1024 * 1024): h.update(block)
        assert file.stat().st_size == row['bytes'] and h.hexdigest() == row['sha256']
        total += row['bytes']
    except (OSError, AssertionError): failures.append(row['id'])
fixtures = query("""SELECT coalesce(json_agg(x),'[]') FROM (SELECT id,name,revision,plugin_version_id FROM projects
 WHERE name LIKE 'G8%' OR name='G7 LOCAL PROTOCOL acceptance' ORDER BY name) x""")
cit = query("""SELECT coalesce(json_agg(x),'[]') FROM (SELECT j.id,j.state,j.result_artifact_id,a.storage_key FROM jobs j
 JOIN artifacts a ON a.id=j.result_artifact_id WHERE j.id IN ('175c30d9-4f95-4297-af3a-28b6e4b4d5e9','51b3554e-6531-4bff-8e17-747790087dcc')) x""")
for row in cit:
    file = (root / row.pop('storage_key')).resolve(strict=True)
    assert file.is_relative_to(root)
    row['result_fixture'] = json.loads(file.read_text())
report = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'volume': a.volume,
          'artifact_count': len(rows), 'artifact_bytes': total, 'hash_failures': failures,
          'projects': fixtures, 'cit': cit}
a.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(bool(failures))
