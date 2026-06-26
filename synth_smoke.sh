#!/usr/bin/env bash
# Fast smoke for the suspect->reproduce->fix pipeline. Runs the genome on ONE small
# synthetic planted-bug repo and asserts it found AND fixed the bug vs the oracle.
# No log-reading, no human in the loop: exit 0 = PASS, exit 1 = FAIL.
#
# Use after any genome change (src/current_version/*) to confirm the plumbing still
# works end to end, before spending 15+ min on a real repo. Run ON mh:
#   ./synth_smoke.sh                  # default: synthbench/paging
#   ./synth_smoke.sh synthbench/locale
set -uo pipefail
cd "$(dirname "$0")"

slug="${1:-synthbench/paging}"
key="${slug/\//__}"
out="results/head/${key}__smoke.out"
mkdir -p results/head

echo ">> [1/3] (re)generate synth repos (root-owned, via harness container)"
docker run --rm -v "$PWD":/work -w /work review-harness python3 synth_bench.py >/dev/null \
  || { echo "FAIL: could not generate synth repos"; exit 1; }

echo ">> [2/3] run pipeline on $slug  (blocks; ~5-10 min) -> $out"
HARNESS_NAME=h-synth-smoke docker/run.sh \
  python -u src/current_version/suspicion.py "$slug" head > "$out" 2>&1
echo "   pipeline summary: $(grep -E '=> bugs' "$out" | tail -1)"

echo ">> [3/3] assert vs oracle"
python3 synth_bench.py check "$slug"
rc=$?
echo ">> result: $([ $rc -eq 0 ] && echo PASS || echo FAIL)  (see $out for the run)"
exit $rc
