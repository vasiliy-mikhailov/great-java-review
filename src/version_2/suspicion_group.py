"""Run the suspicion harness over a GROUP of PRs (the search set) — n>=8 so the reward
averages out per-PR generator variance (one PR is a smoke, not a search signal).

Distinct repos => safe to run in parallel (no git-checkout collision). Each PR is a
SEPARATE process (the suspicion store / pr context are module-level, so one-PR-per-process).
Concurrency capped (SUSP_MAXP, default 4) to bound load on the Qwen endpoint.

Each run saves results/susp_runs/<repo__>__<pr>.json; grade those for the group reward.

  set -a; . ./.env; set +a
  ./venv-oh/bin/python -u src/v8/suspicion_group.py
"""
from __future__ import annotations
import os, subprocess, sys, time

# 8 distinct-repo PRs: 6 general + 2 test, including both fabrication cases (6913, 11945).
GROUP = [
    ("quarkusio/quarkus", "6913"),
    ("hibernate/hibernate-orm", "11945"),
    ("wildfly/wildfly-core", "6222"),
    ("trinodb/trino", "27788"),
    ("spring-projects/spring-boot", "30358"),
    ("eclipse-vertx/vert.x", "4809"),
    ("eclipse-tycho/tycho", "5627"),
    ("square/okhttp", "8829"),
]
# 2 is the most the Qwen endpoint serves well in parallel — beyond that, requests
# contend for GPU, generation slows, and long streams start stalling. Distinct repos
# still make parallelism safe; this just caps how many hit the endpoint at once.
MAXP = int(os.environ.get("SUSP_MAXP", "2"))
# Hard wall-clock per child so a truly wedged PR can't block the batch forever — but set
# very generous (8h): a heavy PR is ~10min generate + 16 fact-checks at ~4min each (full
# code-reading agent loop per check) ≈ 90min, and we never want to kill slow-but-progressing
# work. This backstop is for a genuine hang, not for pacing.
CHILD_TIMEOUT_S = int(os.environ.get("SUSP_CHILD_TIMEOUT_S", "28800"))
HERE = os.path.dirname(os.path.abspath(__file__))


def _launch(repo, pr):
    log = open(f"results/susp_runs/{repo.replace('/', '__')}__{pr}.log", "w")
    return subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "suspicion.py"), repo, pr],
                            stdout=log, stderr=subprocess.STDOUT)


def main():
    os.makedirs("results/susp_runs", exist_ok=True)
    # optional: pass "repo/pr" or "repo#pr" args to run a subset; else the full GROUP.
    group = [tuple(a.replace("#", "/").rsplit("/", 1)) for a in sys.argv[1:]] or GROUP
    todo = list(group)
    running = []          # [proc, repo, pr, started_monotonic]
    t0 = time.monotonic()
    while todo or running:
        while todo and len(running) < MAXP:
            repo, pr = todo.pop(0)
            print(f"launch {repo}#{pr}", flush=True)
            running.append([_launch(repo, pr), repo, pr, time.monotonic()])
        time.sleep(5)
        still = []
        for entry in running:
            p, repo, pr, started = entry
            if p.poll() is not None:
                print(f"done   {repo}#{pr} exit={p.returncode}", flush=True)
            elif time.monotonic() - started > CHILD_TIMEOUT_S:
                p.kill()
                print(f"KILLED  {repo}#{pr} (exceeded {CHILD_TIMEOUT_S}s wall-clock)", flush=True)
            else:
                still.append(entry)
        running = still
    print(f"GROUP RUN COMPLETE ({int(time.monotonic() - t0)}s)", flush=True)


if __name__ == "__main__":
    main()
