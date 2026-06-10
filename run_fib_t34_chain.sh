#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] waiting for compare_hc to free Qwen ==="
while pgrep -f compare_hc.py >/dev/null 2>&1; do sleep 30; done
echo "=== [$(date '+%H:%M:%S')] running in-domain fib sweep with t34 config ==="
./venv/bin/python src/fib_sweep.py qwen 34
echo "=== [$(date '+%H:%M:%S')] FIB t34 DONE ==="
