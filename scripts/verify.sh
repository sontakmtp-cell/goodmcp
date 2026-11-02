#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stage=${1:-G1}
if [ "$#" -gt 0 ]; then shift; fi
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$task_root/scripts/verify.py" --stage "$stage" "$@"
fi
exec python "$task_root/scripts/verify.py" --stage "$stage" "$@"
