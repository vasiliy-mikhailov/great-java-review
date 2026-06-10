#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] JUDGE ALL: scoring the whole heuristic-survivor pool ==="
./venv/bin/python src/quality_judge.py all
echo "=== [$(date '+%H:%M:%S')] quality stats ==="
./venv/bin/python src/quality_judge.py stats
echo "=== [$(date '+%H:%M:%S')] FULL high-quality Fibonacci sweep (t34 config, qwen-gated) ==="
./venv/bin/python src/fib_sweep.py qwen 34
echo "=== [$(date '+%H:%M:%S')] HQ SWEEP DONE ==="
