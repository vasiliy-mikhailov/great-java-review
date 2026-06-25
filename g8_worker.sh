#!/usr/bin/env bash
cd ~/great-java-review || exit 1
mkdir -p results/group8
Q=~/great-java-review/g8_queue.txt
LOCK=~/great-java-review/g8_queue.lock
CHAIN=~/great-java-review/group8b_chain.log
LANE="$1"
log(){ ( flock 9; echo "$1" >> "$CHAIN" ) 9>"$LOCK"; }
while true; do
  entry=$( ( flock 9; line=$(head -n1 "$Q" 2>/dev/null); [ -n "$line" ] && sed -i "1d" "$Q"; printf "%s" "$line" ) 9>"$LOCK" )
  [ -z "$entry" ] && { log "LANE-$LANE-EMPTY $(date +%H:%M:%S)"; break; }
  set -- $entry; repo="$1"; pr="$2"
  slug=$(echo "$repo" | sed "s|/|__|g")__$pr
  dash=$(echo "$repo" | tr / -)
  log "=== [$(date +%H:%M:%S)] LANE-$LANE START $repo#$pr ==="
  rm -f results/group8/$slug.out results/probes/$slug.log results/reasoning/$slug.log results/susp_runs/$slug.json 2>/dev/null
  env HARNESS_NAME=g8-$dash-$pr docker/run.sh python -u src/current_version/suspicion.py "$repo" "$pr" > results/group8/$slug.out 2>&1
  rc=$?
  conf=$(grep -aoE "=> confirmed.*" results/group8/$slug.out | tail -1)
  log "=== [$(date +%H:%M:%S)] LANE-$LANE END $repo#$pr exit=$rc === $conf"
  docker rm -f $(docker ps -aq --filter "name=review-$dash-$pr") >/dev/null 2>&1
done
