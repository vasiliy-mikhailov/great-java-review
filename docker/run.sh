#!/usr/bin/env bash
# Run the v8 harness inside the container. Repo tree + results mounted; Qwen creds passed.
# Usage: docker/run.sh python -u src/current_version/runner.py 37   (or any cmd; default = image smoke)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a   # QWEN_API_KEY / QWEN_BASE_URL
docker run --rm \
  -e QWEN_API_KEY -e QWEN_BASE_URL -e OPENHANDS_SUPPRESS_BANNER=1 \
  -e V8_PRS -e V8_OUT -e V8_TRACE_DIR \
  -v "$PWD":/work -w /work \
  -v oh-m2-cache:/root/.m2 -v oh-gradle-cache:/root/.gradle \
  java-review-v8 "${@:-}"
