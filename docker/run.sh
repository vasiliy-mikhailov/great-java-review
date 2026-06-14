#!/usr/bin/env bash
# Run the harness inside the review-harness container. Repo tree + results mounted; Qwen
# creds passed; the host Docker socket is mounted so sandbox_exec (P17) can spawn sibling
# review-java-<n>-sandbox probe containers.
# Usage: docker/run.sh python -u src/current_version/suspicion.py quarkusio/quarkus 6913
#        docker/run.sh                 (no args = image import smoke)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a   # QWEN_API_KEY / QWEN_BASE_URL
NAME="${HARNESS_NAME:-review-harness-run}"
docker rm -f "$NAME" >/dev/null 2>&1 || true   # clear a stale container so re-runs are clean
docker run --rm --name "$NAME" \
  -e QWEN_API_KEY -e QWEN_BASE_URL -e OPENHANDS_SUPPRESS_BANNER=1 \
  -e SANDBOX_SSH_HOST="" -e OH_MAX_OUT -e SANDBOX_NETWORK \
  -v "$PWD":/work -w /work \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v oh-m2-cache:/root/.m2 -v oh-gradle-cache:/root/.gradle \
  review-harness "$@"
