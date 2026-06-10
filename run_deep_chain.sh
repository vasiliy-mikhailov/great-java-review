#!/usr/bin/env bash
# Autonomous deep-track chain. Honors the single-GitHub-worker rule by waiting
# for the wide crawl to release the worker before doing any GitHub work, then
# runs: collect (10 x reviews_per_reviewer) -> per-reviewer GEPA -> single -> compare.
# The Fibonacci sweep runs independently (Qwen) and is NOT touched here.
set -uo pipefail
cd "$(dirname "$0")"
PY=./venv/bin/python
export PATH="/opt/homebrew/bin:$PATH"
export PYTHONUNBUFFERED=1
log(){ echo "=== [$(date '+%H:%M:%S')] $* ==="; }

# 1) wait for the wide crawl to finish -> exactly ONE github worker at a time
log "waiting for wide crawl to release the GitHub worker..."
while pgrep -f "crawl.py wide" >/dev/null 2>&1; do sleep 60; done
log "GitHub worker free; starting deep collect"

# 2) deep collect (GitHub)
$PY src/crawl.py collect

# 3) per-reviewer GEPA (Qwen), best-covered reviewers with enough material
LOGINS=$($PY - <<'PYEOF'
import json
try:
    d = json.load(open('excellent_reviews.json'))
except Exception:
    print(''); raise SystemExit
rev = d.get('reviewers', {})
items = sorted(rev.items(), key=lambda kv: len(kv[1].get('reviews', [])), reverse=True)
eligible = [l for l, b in items if len(b.get('reviews', [])) >= 25]
print(' '.join(eligible[:10]))
PYEOF
)
echo "per-reviewer logins: $LOGINS"
for L in $LOGINS; do
  OUT="prompts/per_reviewer/${L}.qwen.txt"
  [ -f "$OUT" ] && { echo "skip $L (exists)"; continue; }
  log "GEPA per-reviewer: $L"
  $PY src/gepa_run.py per --login "$L" --profile qwen
done

# 4) single universal prompt (deep) + comparison report
log "single universal prompt GEPA"
[ -f "prompts/single_great.qwen.txt" ] || $PY src/gepa_run.py single --profile qwen
log "comparison report"
$PY src/compare.py qwen

log "DEEP CHAIN DONE"
