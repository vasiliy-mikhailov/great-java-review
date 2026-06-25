#!/usr/bin/env bash
cd /repos || exit 1
REPOS="Aiven-Open/klaw SaptarshiSarkar12/Drifty agroal/agroal apache/accumulo-fluo apache/dubbo apache/flink apache/pulsar eclipse-tycho/tycho eclipse-wildwebdeveloper/wildwebdeveloper quarkiverse/quarkus-mcp-server qubole/rubix rharter/auto-value-moshi sevntu-checkstyle/sevntu.checkstyle smallrye/smallrye-config square/okhttp"
echo "CLONE15-START $(date +%H:%M:%S)"
for r in $REPOS; do
  slug=$(echo "$r" | sed "s|/|__|g")
  if [ -d "$slug/.git" ]; then echo "EXISTS $slug"; continue; fi
  echo "[$(date +%H:%M:%S)] cloning $r ..."
  git clone --quiet "https://github.com/$r" "$slug" && echo "  OK $slug" || echo "  FAIL $slug"
done
echo "CLONE15-DONE $(date +%H:%M:%S)"
