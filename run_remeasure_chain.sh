#!/usr/bin/env bash
# Re-measure Attempt 1 with the FIXED metric (final-answer extraction + robust
# judge parsing, think stays ON). Prompts were built pre-think (valid) -> we
# re-EVALUATE them; the quality gate is re-judged with the fixed SCORE: parser.
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
echo "=== [$(date '+%H:%M:%S')] 1/4 re-judge quality (fixed SCORE: parser, full MR) ==="
./venv/bin/python src/quality_judge.py deep
./venv/bin/python src/quality_judge.py stats
echo "=== [$(date '+%H:%M:%S')] 2/4 compare_hc (fixed metric, existing prompts) ==="
./venv/bin/python src/compare_hc.py qwen
echo "=== [$(date '+%H:%M:%S')] 3/4 group experiment (per vs group-of-5, fixed) ==="
./venv/bin/python src/group_experiment.py qwen 60
echo "=== [$(date '+%H:%M:%S')] 4/4 DONE — re-measured Attempt 1 ==="
