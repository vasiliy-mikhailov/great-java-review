#!/usr/bin/env bash
# Self-healing watchdog for the head corpus rerun. The target lane count is a RUNTIME KNOB read
# from head_lanes.max EVERY cycle: the watchdog STARTS missing lanes 1..MAX while the queue has
# work, and STOPS any lane numbered > MAX — so `echo N > head_lanes.max` scales up OR down live,
# no restart. Flags a lane STUCK only when its REASONING log (token stream) is silent > STUCK_MIN.
# Also watches disk/load. Log: head_watchdog.log; heartbeat: head_watchdog.heartbeat.
cd ~/fix-java-bugs || exit 1
WLOG=~/fix-java-bugs/head_watchdog.log
MAXFILE=~/fix-java-bugs/head_lanes.max; STUCK_MIN=90
wlog(){ echo "[$(date +%F\ %H:%M:%S)] $1" >> "$WLOG"; }
wlog "watchdog START (pid $$) — token-stream stuck-detection"
declare -A FLAGGED
while true; do
  MAX=$(tr -cd '0-9' < "$MAXFILE" 2>/dev/null); [ -z "$MAX" ] && MAX=4
  qn=$(wc -l < head_queue.txt 2>/dev/null || echo 0)
  alive=$(pgrep -af head_worker.sh | grep -oE 'head_worker.sh [0-9]+' | awk '{print $2}' | sort -n | tr '\n' ' ')
  # SCALE UP: start any of lanes 1..MAX that are missing, while the queue has work
  if [ "$qn" -gt 0 ]; then
    for L in $(seq 1 "$MAX"); do
      echo " $alive " | grep -q " $L " || {
        setsid bash head_worker.sh "$L" >/dev/null 2>&1 < /dev/null &
        wlog "START lane $L (max=$MAX; alive=[$alive], queue=$qn)"
      }
    done
  fi
  # SCALE DOWN: stop any live lane numbered > MAX (operator lowered head_lanes.max)
  for L in $alive; do
    [ "$L" -gt "$MAX" ] || continue
    lp=$(pgrep -f "head_worker.sh ${L}\$" | head -1)
    lr=$(grep -aE "LANE-$L START" head_chain.log 2>/dev/null | tail -1 | grep -aoE 'START [^ ]+' | awk '{print $2}')
    lc="review-$(echo "$lr" | tr / -)-head"
    [ -n "$lp" ] && { kill "$lp" 2>/dev/null; sleep 1; kill -9 "$lp" 2>/dev/null; }
    docker rm -f "$lc" >/dev/null 2>&1
    wlog "STOP lane $L (over max=$MAX) pid=$lp container=$lc"
  done
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
  echo "$(date +%H:%M) q=$qn lanes=[$alive] max=$MAX load=$la disk=${use}%" >> ~/fix-java-bugs/head_watchdog.heartbeat
  sleep 300
done
