"""Operator health snapshot; does not expose private logs or credentials."""
import datetime
import json
from pathlib import Path
import shutil

root = Path('/opt/goodmcp')
state = root / 'state'
state.mkdir(exist_ok=True, mode=0o755)
disk = shutil.disk_usage(root)
used = round(100 * disk.used / disk.total, 2)
flag = state / 'disk-full'
if used >= 85:
    flag.touch(mode=0o644)
else:
    flag.unlink(missing_ok=True)
backup = root / 'backups/last-success.json'
now = datetime.datetime.now(datetime.timezone.utc)
age = None
if backup.is_file():
    age = (now - datetime.datetime.fromisoformat(json.loads(backup.read_text())['completed_at'])).total_seconds()
report = {'observed_at': now.isoformat(), 'disk_used_percent': used,
          'disk_warning': used >= 70, 'new_uploads_paused': used >= 85,
          'backup_age_seconds': age, 'backup_overdue': age is None or age > 86400,
          'off_vps_automatic': False, 'off_vps_note': 'R2 deferred by owner; encrypted copy must be retrieved separately.'}
(state / 'health.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
