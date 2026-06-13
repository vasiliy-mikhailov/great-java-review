# v8 harness runtime: OpenHands runs IN this container (P12).
# Lean base now; JDK/maven present for the future in-container reality-check `verify` tool.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ripgrep ca-certificates default-jdk-headless maven \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY docker/requirements-oh.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

ENV OPENHANDS_SUPPRESS_BANNER=1 PYTHONUNBUFFERED=1
# code + data/repos + results are MOUNTED at runtime (5.3G of repos — never baked).
CMD ["python","-c","import openhands.sdk, litellm, openai; print('v8 image OK: openhands-sdk + litellm + openai import clean')"]
