#!/usr/bin/env bash
cd ~/great-java-review || exit 1
while read repo; do
  [ -z "$repo" ] && continue; case "$repo" in \#*) continue;; esac
  slug=$(echo "$repo" | sed "s|/|__|g"); d=data/repos/$slug
  if [ ! -d "$d" ]; then echo "clone $repo"; git clone --quiet "https://github.com/$repo" "$d" || { echo "CLONE FAIL $repo"; continue; }; fi
  git -C "$d" remote set-head origin -a >/dev/null 2>&1
  b=$(git -C "$d" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed "s|origin/||"); b=${b:-main}
  git -C "$d" fetch --quiet origin "$b" && git -C "$d" checkout --quiet "$b" && git -C "$d" reset --hard --quiet "origin/$b"
  echo "  ready $repo @ $(git -C "$d" rev-parse --short HEAD 2>/dev/null) ($b)"
done < "$1"
echo "=== prep done; launching 2 head lanes ==="
nohup bash head_worker.sh 1 >/dev/null 2>&1 &
nohup bash head_worker.sh 2 >/dev/null 2>&1 &
