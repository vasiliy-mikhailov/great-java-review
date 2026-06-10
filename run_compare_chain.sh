#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] waiting for build_prompts to finish ==="
while pgrep -f build_prompts.py >/dev/null 2>&1; do sleep 30; done
echo "=== [$(date '+%H:%M:%S')] build done; verifying no leaks ==="
./venv/bin/python - <<'PY'
import re, glob, sys
bad = [f for f in glob.glob("prompts/per_reviewer/*.qwen.txt") + ["prompts/single_great.qwen.txt"]
       if re.search(r"reference\s+review", open(f).read(), re.I)]
print("leaky prompts:", bad if bad else "NONE - all clean")
sys.exit(1 if bad else 0)
PY
if [ $? -ne 0 ]; then echo "ABORT: leaks remain"; exit 1; fi
echo "=== [$(date '+%H:%M:%S')] running compare ==="
./venv/bin/python src/compare.py qwen
echo "=== [$(date '+%H:%M:%S')] COMPARE DONE ==="
