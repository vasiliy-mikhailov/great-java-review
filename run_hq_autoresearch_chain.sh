#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] waiting for fib_sweep (t34) to free Qwen ==="
while pgrep -f fib_sweep.py >/dev/null 2>&1; do sleep 30; done
echo "=== [$(date '+%H:%M:%S')] Qwen quality-judging vietj's units (populate cache) ==="
./venv/bin/python src/quality_judge.py reviewer vietj
echo "=== [$(date '+%H:%M:%S')] HIGH-QUALITY (qwen-gated) vietj AutoResearch ==="
./venv/bin/python src/autoresearch.py qwen
echo "=== [$(date '+%H:%M:%S')] HQ AUTORESEARCH DONE ==="
