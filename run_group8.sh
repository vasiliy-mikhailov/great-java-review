#!/usr/bin/env bash
cd ~/great-java-review || exit 1
mkdir -p results/group8
PRS=(
  "quarkusio/quarkus 6913"
  "eclipse-vertx/vert.x 4809"
  "hibernate/hibernate-orm 11945"
  "spring-projects/spring-boot 30358"
  "trinodb/trino 27788"
  "wildfly/wildfly-core 6222"
  "netty/netty 14487"
  "apache/kafka 17565"
)
echo "GROUP8-START $(date +%F\ %H:%M:%S)"
for entry in "${PRS[@]}"; do
  set -- $entry; repo=$1; pr=$2
  slug=$(echo "$repo" | tr / _)__$pr
  dash=$(echo "$repo" | tr / -)
  echo "=== [$(date +%H:%M:%S)] START $repo#$pr ==="
  rm -f results/group8/$slug.out results/probes/$slug.log results/reasoning/$slug.log results/susp_runs/$slug.json 2>/dev/null
  env HARNESS_NAME=g8-$dash-$pr docker/run.sh python -u src/current_version/suspicion.py "$repo" "$pr" > results/group8/$slug.out 2>&1
  rc=$?
  echo "=== [$(date +%H:%M:%S)] END $repo#$pr exit=$rc ==="
  grep -aoE "=> confirmed.*" results/group8/$slug.out | tail -1
  docker rm -f $(docker ps -aq --filter "name=review-$dash-$pr") >/dev/null 2>&1
done
echo "GROUP8-DONE $(date +%F\ %H:%M:%S)"
