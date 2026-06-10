#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] waiting for compare_hc to free Qwen ==="
while pgrep -f compare_hc.py >/dev/null 2>&1; do sleep 30; done
echo "=== [$(date '+%H:%M:%S')] per-reviewer vs group-of-5 GEPA (HQ full-MR) ==="
./venv/bin/python src/group_experiment.py qwen 60
echo "=== [$(date '+%H:%M:%S')] GROUP EXPERIMENT DONE ==="
