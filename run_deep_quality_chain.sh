#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] JUDGE DEEP: scoring full-MR reviews with reasoning ==="
./venv/bin/python src/quality_judge.py deep
echo "=== [$(date '+%H:%M:%S')] quality stats ==="
./venv/bin/python src/quality_judge.py stats
echo "=== [$(date '+%H:%M:%S')] HIGH-QUALITY full-MR comparison (baseline vs per-reviewer vs single) ==="
./venv/bin/python src/compare_hc.py qwen
echo "=== [$(date '+%H:%M:%S')] DEEP HQ DONE ==="
