# Harness runtime: OpenHands runs IN this container (P12). It spawns per-PR sibling
# `review-java-<n>-sandbox` probe containers via the mounted host Docker socket (P17),
# so it carries the docker CLI. JDK/maven stay for ad-hoc in-container checks.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ripgrep ca-certificates curl default-jdk-headless maven \
    && rm -rf /var/lib/apt/lists/*

# docker CLI (client only) — talks to the host daemon via the bind-mounted /var/run/docker.sock
ARG DOCKER_CLI_VERSION=27.5.1
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz \
      | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && docker --version

WORKDIR /work
COPY docker/requirements-oh.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

ENV OPENHANDS_SUPPRESS_BANNER=1 PYTHONUNBUFFERED=1
# code + data/repos + results are MOUNTED at runtime (never baked).
CMD ["python","-c","import openhands.sdk, litellm, openai; print('review-harness image OK: openhands-sdk + litellm + openai import clean')"]
