#!/usr/bin/env bash
# End-to-end, resumable pipeline. Safe to re-run: every stage skips work that
# is already complete. Single GitHub worker throughout (no parallel git).
set -uo pipefail
cd "$(dirname "$0")"
PY=./venv/bin/python
PROFILE="${1:-qwen}"
export PATH="/opt/homebrew/bin:$PATH"   # for gh

log(){ echo "=== [$(date '+%H:%M:%S')] $* ==="; }

log "STAGE 1/6 discover (identify reviewers)"
$PY src/crawl.py discover

log "STAGE 2/6 collect (10 reviewers x 300 reviews -> excellent_reviews.json)"
$PY src/crawl.py collect

log "STAGE 3/6 per-reviewer GEPA ($PROFILE)"
LOGINS=$($PY - <<'PYEOF'
import json
d=json.load(open('excellent_reviews.json'))
rev=d['reviewers']
# reviewers with enough material to optimize, best-covered first
items=sorted(rev.items(), key=lambda kv: len(kv[1]['reviews']), reverse=True)
out=[l for l,b in items if len(b['reviews'])>=25][:10]
print(' '.join(out))
PYEOF
)
echo "reviewers: $LOGINS"
for L in $LOGINS; do
  OUT="prompts/per_reviewer/${L}.${PROFILE}.txt"
  if [ -f "$OUT" ]; then echo "skip $L (exists)"; continue; fi
  log "GEPA per-reviewer: $L"
  $PY src/gepa_run.py per --login "$L" --profile "$PROFILE"
done

log "STAGE 4/6 single universal prompt GEPA ($PROFILE)"
if [ ! -f "prompts/single_great.${PROFILE}.txt" ]; then
  $PY src/gepa_run.py single --profile "$PROFILE"
else
  echo "skip single (exists)"
fi

log "STAGE 5/6 comparison report ($PROFILE)"
$PY src/compare.py "$PROFILE"

log "STAGE 6/6 Fibonacci scaling sweep ($PROFILE): universal prompt vs #reviewers (k=1,2,3,5,8,...)"
$PY src/fib_sweep.py "$PROFILE"

log "PIPELINE DONE"
