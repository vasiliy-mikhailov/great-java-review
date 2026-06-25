#!/usr/bin/env bash
# Two lightweight background loops that turn the one-pass batch into CONTINUOUS exploration,
# without restarting (and orphaning) the busy head/judge lanes.
cd ~/great-java-review || exit 1
LOCK=~/great-java-review/head_queue.lock
case "$1" in
  refill)
    # Keep head_queue topped up from the master cycle list so the lanes never drain & exit —
    # they round-robin through every repo forever. JSONs never cache-block a re-hunt.
    while true; do
      n=$(wc -l < head_queue.txt 2>/dev/null || echo 0)
      if [ "${n:-0}" -lt 6 ]; then
        ( flock 9; cat head_cycle.txt >> head_queue.txt ) 9>"$LOCK"
        echo "[$(date +%F\ %H:%M:%S)] refilled queue (was $n) -> $(wc -l < head_queue.txt)" >> results/refill.log
      fi
      sleep 120
    done ;;
  harvest)
    # Preserve every REAL verdict across rounds before re-hunts overwrite the judged JSONs.
    while true; do
      python3 harvest_candidates.py >> results/harvest.log 2>&1
      sleep 120
    done ;;
  *) echo "usage: explore_daemons.sh {refill|harvest}"; exit 1 ;;
esac
