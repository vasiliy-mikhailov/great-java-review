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

_SESSION = {"name": None, "log": None, "base": None, "worktree": None}


def _run(remote_cmd: str, stdin: str = "", timeout: int = 240):
    """Run one docker command against the daemon — locally (default) or over a single SSH
    call (SANDBOX_SSH_HOST set). Local mode talks to the host socket from inside the harness
    container (docker-out-of-docker), spawning probe containers as siblings."""
    argv = ["ssh", SSH_HOST, remote_cmd] if SSH_HOST else ["bash", "-lc", remote_cmd]
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)


def start(repo: str, pr: str, jdk: int = DEFAULT_JDK, log_path: str | None = None) -> str:
    """Per-session JDK sandbox with BOTH versions mounted: the base tree (prev) at /src/old and a
    pr-<pr>-head worktree (post-PR) at /src/new — so tools read/compile whichever version is the
    target. Default cwd is /src/new (what you verify). Idempotent."""
    image = IMAGE_FOR.get(jdk, IMAGE_FOR[DEFAULT_JDK])
    name = "review-" + repo.replace("/", "-") + "-" + str(pr)
    net = os.environ.get("SANDBOX_NETWORK", "mvn-cache")
    netarg = f"--network {net} " if net else ""
    # HOST_WORKDIR = the host path that is the harness's /work; -v paths are resolved host-side
    # (DooD), and the harness sees the same dirs at /work/... so it can run git there.
    host_work = os.environ.get("HOST_WORKDIR", os.getcwd())
    slug = repo.replace('/', '__')
    old_host, new_host = f"{host_work}/data/repos/{slug}", f"{host_work}/data/repos/{slug}__new-{pr}"
    cbase, cnew = f"/work/data/repos/{slug}", f"/work/data/repos/{slug}__new-{pr}"
    # create the post-PR worktree from the pr-head ref (fall back to base if the ref is missing)
    _run(f"git -C {cbase} worktree remove -f {cnew} >/dev/null 2>&1; git -C {cbase} worktree prune >/dev/null 2>&1; "
         f"git -C {cbase} worktree add -f {cnew} pr-{pr}-head >/dev/null 2>&1 || "
         f"git -C {cbase} worktree add -f {cnew} HEAD >/dev/null 2>&1")
    _run(f"docker rm -f {name} >/dev/null 2>&1; "
         f"docker run -d {netarg}-v {old_host}:/src/old -v {new_host}:/src/new -w /src/new "
         f"--name {name} {image} sleep infinity")
    _SESSION.update(name=name, log=log_path, base=cbase, worktree=cnew)
    return name


def workdir(version: str = "new") -> str | None:
    """Harness-container path to the checked-out tree for `version` (new = post-PR worktree,
    old = base), or None if no session. Both live under /work (bind-mounted into the harness
    container), so they are valid working dirs for the local read tools too — not only the
    sandbox's /src/<version>."""
    return _SESSION.get("base") if version == "old" else _SESSION.get("worktree")


def exec_(command: str, timeout_s: int = 120, version: str = "new") -> tuple[int, str]:
    """Run `command` (bash) inside the session container, cwd = /src/<version> (new = post-PR,
    old = base); return (exit_code, output). Output is combined stdout+stderr, tail-capped. The
    probe is wrapped in an INNER `timeout -k` so it self-exits even if the client is interrupted.
    """
    name = _SESSION["name"]
    if not name:
        return 127, "sandbox not started (call start())"
    wd = "/src/old" if version == "old" else "/src/new"
    inner = f"cd {wd} && timeout -k 5 {timeout_s} bash -s"
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
        base, wt = _SESSION.get("base"), _SESSION.get("worktree")
        if base and wt:                       # reap the post-PR worktree we created in start()
            _run(f"git -C {base} worktree remove -f {wt} >/dev/null 2>&1; "
                 f"git -C {base} worktree prune >/dev/null 2>&1", timeout=60)
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
