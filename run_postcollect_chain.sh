#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] waiting for expanded collect to finish ==="
while pgrep -f "crawl.py collect" >/dev/null 2>&1; do sleep 120; done
echo "=== [$(date '+%H:%M:%S')] collect done; quality-judging the FULL expanded pool (full-MR, incremental) ==="
./venv/bin/python src/quality_judge.py deep
./venv/bin/python src/quality_judge.py stats
echo "=== [$(date '+%H:%M:%S')] EXPANDED POOL JUDGED ==="
