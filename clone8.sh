#!/usr/bin/env bash
cd ~/great-java-review/data/repos || exit 1
echo "CLONE-START $(date +%H:%M:%S)"
if [ ! -d netty__netty ]; then
  git clone --quiet https://github.com/netty/netty netty__netty && \
  git -C netty__netty fetch --quiet origin pull/14487/head:pr-14487-head && \
  git -C netty__netty checkout --quiet 2e4fbee92f465e96e5aff894e51b91135be174a2 && echo "NETTY-OK"
else echo "NETTY-EXISTS"; fi
if [ ! -d apache__kafka ]; then
  git clone --quiet https://github.com/apache/kafka apache__kafka && \
  git -C apache__kafka fetch --quiet origin pull/17565/head:pr-17565-head && \
  git -C apache__kafka checkout --quiet 25e8e4cbcf336058726848c9a5e80edb407fc2c2 && echo "KAFKA-OK"
else echo "KAFKA-EXISTS"; fi
echo "CLONE-DONE $(date +%H:%M:%S)"
