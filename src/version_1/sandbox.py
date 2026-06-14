"""Remote Docker verification sandbox (contract P17) — run pretty much anything in a
per-session Java container on server2, so the fact-checker (P15) PROVES a suspicion by
execution instead of imagining it.

Talks to the Docker daemon LOCALLY by default (the harness runs in its own container on the
build host with the host socket mounted, so probe containers are spawned as SIBLINGS); set
SANDBOX_SSH_HOST=mh to drive the daemon over SSH from the laptop instead. One NAMED, persistent
container per review session (`review-<repo>-<pr>`) from a `review-java-<n>-sandbox` image;
every probe is `docker exec`'d into it and logged. The container is the only place
untrusted/build code runs — never the host.

Two hard substrate rules (from the bump_java_version cluster, P6) are baked in here:
  - INNER `timeout -k` on every probe: an ssh/exec-client timeout does NOT kill the
    container, so a hung build would survive holding cache locks — the container must
    self-bound.
  - the container is removed in a finally (`stop`), and we never write json-file logs
    unbounded (probes log to a host file, not the container's stdout).
"""
from __future__ import annotations
import os, subprocess, time

# Where the Docker daemon is. Empty (default) = LOCAL docker — the harness runs ON the build
# host inside its own container with the host socket mounted, spawning probe containers as
# SIBLINGS. Set SANDBOX_SSH_HOST=mh to drive the remote daemon over SSH from the laptop.
SSH_HOST = os.environ.get("SANDBOX_SSH_HOST", "")
# JDK major -> image. All are `maven:3.9-eclipse-temurin-<n>` tagged `review-java-<n>-sandbox`.
IMAGE_FOR = {8: "review-java-8-sandbox", 11: "review-java-11-sandbox",
             17: "review-java-17-sandbox", 21: "review-java-21-sandbox"}
DEFAULT_JDK = 21

_SESSION = {"name": None, "log": None}


def _run(remote_cmd: str, stdin: str = "", timeout: int = 240):
    """Run one docker command against the daemon — locally (default) or over a single SSH
    call (SANDBOX_SSH_HOST set). Local mode talks to the host socket from inside the harness
    container (docker-out-of-docker), spawning probe containers as siblings."""
    argv = ["ssh", SSH_HOST, remote_cmd] if SSH_HOST else ["bash", "-lc", remote_cmd]
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)


def start(repo: str, pr: str, jdk: int = DEFAULT_JDK, log_path: str | None = None) -> str:
    """Create the per-session container (idempotent: removes a stale one first)."""
    image = IMAGE_FOR.get(jdk, IMAGE_FOR[DEFAULT_JDK])
    name = "review-" + repo.replace("/", "-") + "-" + str(pr)
    _run(f"docker rm -f {name} >/dev/null 2>&1; "
         f"docker run -d --name {name} -w /work {image} sleep infinity")
    _SESSION["name"] = name
    _SESSION["log"] = log_path
    return name


def exec_(command: str, timeout_s: int = 120) -> tuple[int, str]:
    """Run `command` (bash) inside the session container; return (exit_code, output).

    Output is combined stdout+stderr, tail-capped. The probe is wrapped in an INNER
    `timeout -k` so it self-exits even if the ssh client is interrupted.
    """
    name = _SESSION["name"]
    if not name:
        return 127, "sandbox not started (call start())"
    inner = f"timeout -k 5 {timeout_s} bash -s"
    remote = f"docker exec -i {name} bash -lc '{inner}'"
    try:
        r = _run(remote, stdin=command, timeout=timeout_s + 30)
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = 124, "(ssh client timed out; inner timeout should have bounded the container)"
    out = out[-8000:]
    if _SESSION["log"]:
        try:
            with open(_SESSION["log"], "a") as f:
                f.write(f"\n$ {command}\n[exit {rc}]\n{out}\n")
        except Exception:  # noqa: BLE001
            pass
    return rc, out


def stop():
    name = _SESSION["name"]
    if name:
        _run(f"docker rm -f {name} >/dev/null 2>&1", timeout=60)
        _SESSION["name"] = None


if __name__ == "__main__":   # smoke: prove a self-contained logic claim by execution
    start("smoke/test", "0", jdk=21)
    try:
        rc, out = exec_(
            "mkdir -p /work && cat > /work/M.java <<'EOF'\n"
            "public class M { public static void main(String[] a){ System.out.println(\"ran on \"+System.getProperty(\"java.version\")); } }\n"
            "EOF\n"
            "cd /work && javac M.java && java M")
        print(f"exit={rc}\n{out}")
    finally:
        stop()
