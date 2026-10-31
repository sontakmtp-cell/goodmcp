#!/bin/sh
# New Hub data only. Local encrypted repository until off-VPS R2 is enabled.
set -eu
cd /opt/goodmcp
exec 9>/run/lock/goodmcp-backup.lock
flock -n 9 || exit 0
export RESTIC_REPOSITORY=/opt/goodmcp/backups/repository
export RESTIC_PASSWORD_FILE=/opt/goodmcp/secrets/restic_password
umask 077
mkdir -p backups/staging
if [ ! -f "$RESTIC_REPOSITORY/config" ]; then restic init; fi
restart_writers() { /opt/goodmcp/compose up -d --wait --no-build api auth worker dispatcher; }
trap restart_writers EXIT HUP INT TERM
./compose stop -t 40 api auth worker dispatcher
./compose exec -T postgres pg_dump -U postgres -d goodmcp -Fc > backups/staging/database.dump
docker volume inspect goodmcp-prod_artifacts --format '{{.Mountpoint}}' > backups/staging/artifact-volume-path
artifacts=$(cat backups/staging/artifact-volume-path)
case "$artifacts" in /var/lib/docker/volumes/goodmcp-prod_artifacts/_data) ;; *) echo 'Unexpected artifact source' >&2; exit 1;; esac
restic backup --json --tag goodmcp-production "$artifacts" backups/staging releases/g8 finance secrets deploy.env compose approved-finance.oci.tar app-images.tar postgres-image.tar --exclude /opt/goodmcp/secrets/restic_password > backups/last-run.jsonl
restart_writers
trap - EXIT HUP INT TERM
restic check
restic forget --keep-daily 7 --keep-weekly 4 --prune
python3 - <<'PY'
import json,datetime,pathlib
p=pathlib.Path('/opt/goodmcp/backups/last-run.jsonl')
summary=next(x for x in reversed([json.loads(line) for line in p.read_text().splitlines()]) if x.get('message_type')=='summary')
pathlib.Path('/opt/goodmcp/backups/last-success.json').write_text(json.dumps({'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'snapshot_id':summary['snapshot_id'],'off_vps_automatic':False})+'\n')
PY
