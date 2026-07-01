#!/usr/bin/env bash
# Self-healing watchdog for the head corpus rerun. Restarts dead lanes (only while the queue
# has work), and flags a lane as STUCK only when its REASONING log (the token stream) goes
# silent > STUCK_MIN — i.e. it genuinely stopped producing tokens (operator's criterion).
# Also watches disk/load. Read head_watchdog.log; heartbeat in head_watchdog.heartbeat.
cd ~/fix-java-bugs || exit 1
WLOG=~/fix-java-bugs/head_watchdog.log
NLANES=5; STUCK_MIN=90
wlog(){ echo "[$(date +%F\ %H:%M:%S)] $1" >> "$WLOG"; }
wlog "watchdog START (pid $$) — token-stream stuck-detection"
declare -A FLAGGED
while true; do
  qn=$(wc -l < head_queue.txt 2>/dev/null || echo 0)
  alive=$(pgrep -af head_worker.sh | grep -oE 'head_worker.sh [0-9]+' | awk '{print $2}' | sort -n | tr '\n' ' ')
  nalive=$(echo $alive | wc -w)
  # restart missing lanes only while there is queued work
  if [ "$qn" -gt 0 ] && [ "$nalive" -lt "$NLANES" ]; then
    for L in $(seq 1 $NLANES); do
      if ! echo " $alive " | grep -q " $L "; then
        setsid bash head_worker.sh "$L" >/dev/null 2>&1 < /dev/null &
        wlog "RESTARTED lane $L (was missing; queue=$qn, alive=[$alive])"
      fi
    done
  fi
  # STUCK = a running harness whose reasoning log (token stream) has not advanced in STUCK_MIN
  for c in $(docker ps --format '{{.Names}}' | grep -E '^h-'); do
    spec=$(docker inspect "$c" --format '{{range .Config.Cmd}}{{println .}}{{end}}{{range .Args}}{{println .}}{{end}}' 2>/dev/null)
    repo=$(echo "$spec" | grep -E '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$' | head -1)
    slug=${repo//\//__}
    [ -z "$slug" ] && continue
    f="results/reasoning/${slug}__head.log"
    [ -f "$f" ] || continue
    age=$(( ($(date +%s) - $(stat -c %Y "$f")) / 60 ))
    if [ "$age" -gt "$STUCK_MIN" ]; then
      if [ -z "${FLAGGED[$slug]:-}" ]; then
        wlog "STUCK? $slug — reasoning log silent ${age}min (stopped producing tokens; NOT killed; flag to operator)"
        FLAGGED[$slug]=1
      fi
    else
      unset 'FLAGGED[$slug]'
    fi
  done
  use=$(df / | awk 'NR==2{gsub(/%/,"",$5); print $5}')
  [ "$use" -gt 88 ] && { wlog "DISK ${use}% — pruning dangling images"; docker image prune -f >/dev/null 2>&1; }
  la=$(awk '{print $1}' /proc/loadavg)
  echo "$(date +%H:%M) q=$qn lanes=[$alive] load=$la disk=${use}%" >> ~/fix-java-bugs/head_watchdog.heartbeat
  sleep 300
done
