#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$task_root/scripts/verify.py" --stage "${1:-G1}"
fi
exec python "$task_root/scripts/verify.py" --stage "${1:-G1}"
