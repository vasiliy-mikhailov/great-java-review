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

# no_cheat: when on, exec_ blocks the run (removes the files + WITHHOLDS the output) if the command
# created any new source file — EXCEPT a legitimate regression test under src/test/ named *Test/*Tests/*IT
# (that's the one artifact the reproducer is allowed to author, via create_test; it can't be a production
# stub). A new file under src/main, or any *.java dropped in /tmp /root /home, is still a copy/stub/driver
# and stays blocked. Set per-agent by the harness.
_NO_NEW = {"on": False}
# matches a new file we ALLOW: under a src/test/ root with a JUnit *Test/*Tests/*IT name.
_TEST_NEW_OK = r"/src/test/.*(Test|Tests|IT)\.java$"


def set_no_new_files(on: bool):
    _NO_NEW["on"] = bool(on)


def detect_jdk(repo_dir: str) -> int:
    """Pick the BUILD jdk from the repo's declared Java level — a WRONG jdk yields FALSE compile errors
    that poison every verdict (quarkus#6913: source 1.8 but built JDK 21 -> `package sun.misc does not
    exist` + enforcer reject). Read maven.compiler.{release,target,source} / <java.version> from the
    poms, take the highest, and map to an available image. <=8 builds on 11 (JDK 11 has sun.misc and can
    target 8; most 'java 8' enforcers want 11+); 11->11; 12-17->17; >=18->21. Default 21 if undeclared."""
    import glob as _glob, re as _re
    levels = []
    poms = _glob.glob(os.path.join(repo_dir, "**", "pom.xml"), recursive=True)[:400]
    for p in poms:
        try:
            t = open(p, errors="ignore").read()
        except Exception:  # noqa: BLE001
            continue
        for m in _re.findall(r"maven\.compiler\.(?:release|target|source)>\s*(?:1\.)?(\d{1,2})", t):
            levels.append(int(m))
        for m in _re.findall(r"<java\.version>\s*(?:1\.)?(\d{1,2})", t):
            levels.append(int(m))
    if not levels:
        return DEFAULT_JDK
    lvl = max(levels)
    # build on the lowest LTS that safely compiles the level. <=8 builds on 11 (the quarkus lesson:
    # Java-8-target code overwhelmingly builds on 11+ with sun.misc intact; the 8 image stays available
    # for a manual jdk= override on a true-Java-8 project that uses APIs removed in 11, e.g. JAXB).
    return 11 if lvl <= 11 else 17 if lvl <= 17 else 21 if lvl <= 21 else 25


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
    # snapshot the existing source files — exec_'s no_cheat guard treats any .java NOT in here as a
    # new file the reproducer created (a copy/stub), and blocks it. git is unavailable in the sandbox
    # (worktree .git not mounted), so a find-snapshot is how we tell new from modified.
    _run(f"docker exec {name} bash -lc \"find /src/new -name '*.java' 2>/dev/null | sort > /tmp/.known_java\" "
         f">/dev/null 2>&1")
    _SESSION.update(name=name, log=log_path, base=cbase, worktree=cnew)
    return name


def workdir(version: str = "new") -> str | None:
    """Harness-container path to the checked-out tree for `version` (new = post-PR worktree,
    old = base), or None if no session. Both live under /work (bind-mounted into the harness
    container), so they are valid working dirs for the local read tools too — not only the
    sandbox's /src/<version>."""
    return _SESSION.get("base") if version == "old" else _SESSION.get("worktree")


def reset_clean():
    """Reset BOTH mounted trees to pristine (HEAD), so a fact-check starts from clean source no matter
    what the prover wrote/compiled/edited — it works in /src/new like a normal checkout and we reset it.
    The git reset MUST run harness-side (via _run): the worktree's .git points at a /work host path that
    does not resolve inside the sandbox container. Cheap when nothing changed; clears stray test files,
    source edits, and build artifacts. Exposed both as the auto-reset before each check AND the
    reset_workspace tool the prover can call itself."""
    for tree in (_SESSION.get("worktree"), _SESSION.get("base")):
        if tree:
            _run(f"git -C {tree} checkout -- . >/dev/null 2>&1; "
                 f"git -C {tree} clean -fdx >/dev/null 2>&1", timeout=180)


def diff_numstat(version: str = "new"):
    """Per-file (added+deleted) line counts in the worktree vs HEAD: list of (path, lines). Runs harness-side
    (the worktree .git resolves under /work). Used to MEASURE the solver's production patch size for the
    reward — honest, not the model's self-reported diff."""
    tree = _SESSION.get("base") if version == "old" else _SESSION.get("worktree")
    if not tree:
        return []
    try:
        r = _run(f"git -C {tree} diff --numstat", timeout=60)
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for ln in (r.stdout or "").splitlines():
        parts = ln.split("\t")
        if len(parts) == 3:
            a, d, path = parts
            n = (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)
            rows.append((path, n))
    return rows


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
    if _NO_NEW["on"]:   # no_cheat: block + WITHHOLD output if the command created any new source file
        # ... except a legit regression test under src/test/ (allowed: it's create_test's one artifact).
        guard = ("NEW=$( { comm -13 /tmp/.known_java <(find /src/new -name '*.java' 2>/dev/null | sort) "
                 f"| grep -vE '{_TEST_NEW_OK}'; "
                 "find /tmp /root /home -name '*.java' 2>/dev/null; } | sort -u )\n"
                 "if [ -n \"$NEW\" ]; then echo \"$NEW\" | xargs -r rm -f; echo __NEWFILES__; echo \"$NEW\"; fi\n")
        try:
            g = _run(f"docker exec -i {name} bash -lc 'bash -s'", stdin=guard, timeout=60)
            gout = g.stdout or ""
        except Exception:  # noqa: BLE001
            gout = ""
        if "__NEWFILES__" in gout:
            files = gout.split("__NEWFILES__", 1)[1].strip()
            rc, out = 1, ("[no_cheat] BLOCKED — your command created new source file(s); they were removed and "
                          "the run output is withheld. You may ONLY modify EXISTING files (add logging) and run "
                          "the project's existing tests/build — never write copies, stubs, or standalone drivers:\n"
                          + files)
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
