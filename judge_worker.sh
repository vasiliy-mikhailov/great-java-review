#!/usr/bin/env bash
cd ~/great-java-review || exit 1
LOCK=~/great-java-review/judge.lock
CHAIN=~/great-java-review/judge_chain.log
LANE="$1"
log(){ ( flock 9; echo "$1" >> "$CHAIN" ) 9>"$LOCK"; }
while true; do
  # atomically claim the next completed-hunt repo whose judged output is STALE (older than the registry) or
  # missing, and with no in-progress claim for the CURRENT registry. -nt is re-hunt-aware: a fresh re-hunt
  # bumps susp_runs' mtime, so its old judged/.json + .claim become stale and the repo is re-judged. (deep, no caps)
  repo=$( ( flock 9
    for f in results/susp_runs/*__head.json; do
      slug=$(basename "$f" .json)
      [ "results/judged/$slug.json" -nt "$f" ] && continue    # judged AND newer than the registry -> already fresh
      [ "results/judged/$slug.claim" -nt "$f" ] && continue   # a judge for THIS registry is already in flight
      r=$(python3 -c "import json;print(json.load(open('$f'))['repo'])" 2>/dev/null)
      [ -z "$r" ] && continue
      mkdir -p results/judged; touch "results/judged/$slug.claim"
      echo "$r"; break
    done ) 9>"$LOCK" )
  [ -z "$repo" ] && { sleep 300; continue; }   # nothing stale to judge — wait for a hunt/re-hunt to land
  dash=$(echo "$repo" | tr / -)
  log "=== [$(date +%F\ %H:%M:%S)] JUDGE-$LANE START $repo ==="
  HARNESS_NAME=judge-$dash docker/run.sh python -u src/current_version/suspicion.py "$repo" judge > results/judge_${dash}.out 2>&1
  log "=== [$(date +%F\ %H:%M:%S)] JUDGE-$LANE END $repo === $(grep -aoE 'judged REAL for.*' results/judge_${dash}.out | tail -1)"
done
