#!/usr/bin/env bash
cd ~/fix-java-bugs || exit 1
Q=~/fix-java-bugs/head_queue.txt; LOCK=~/fix-java-bugs/head_queue.lock; CHAIN=~/fix-java-bugs/head_chain.log
LANE="$1"
log(){ ( flock 9; echo "$1" >> "$CHAIN" ) 9>"$LOCK"; }
while true; do
  repo=$( ( flock 9; line=$(head -n1 "$Q" 2>/dev/null); [ -n "$line" ] && sed -i "1d" "$Q"; printf "%s" "$line" ) 9>"$LOCK" )
  [ -z "$repo" ] && { log "LANE-$LANE EMPTY $(date +%F\ %H:%M:%S)"; break; }
  dash=$(echo "$repo" | tr / -); slug=$(echo "$repo" | sed "s|/|__|g")
  log "=== [$(date +%F\ %H:%M:%S)] LANE-$LANE START $repo ==="
  HARNESS_NAME=h-$dash docker/run.sh python -u src/current_version/suspicion.py "$repo" head > results/head/${slug}__head.out 2>&1
  rc=$?
  summary=$(grep -aoE "=> bugs.*" results/head/${slug}__head.out | tail -1)
  log "=== [$(date +%F\ %H:%M:%S)] LANE-$LANE END $repo exit=$rc === $summary"
  docker rm -f $(docker ps -aq --filter "name=review-$dash-head") >/dev/null 2>&1
done
