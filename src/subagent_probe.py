"""Rerun a few PRs with PER-CALL logging ON, to capture the SUBAGENT journeys (intent →
calls → sequence → wall time) that the orchestrator event dump can't see. Reuses cached
repos; does NOT touch the running baseline (separate process, own output files).

  ./venv-oh/bin/python -u src/subagent_probe.py dubbo:13489 netty:14487
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import call_log  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
import dataset as ds  # noqa: E402

REPOS = {"dubbo": "apache/dubbo", "netty": "netty/netty", "accumulo-fluo": "apache/accumulo-fluo",
         "tycho": "eclipse-tycho/tycho", "quarkus": "quarkusio/quarkus"}
OUTDIR = "results/traces_sub"


def main():
    args = sys.argv[1:] or ["dubbo:13489"]
    imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values() for x in v}
    os.makedirs(OUTDIR, exist_ok=True)
    for a in args:
        short, pr = a.split(":"); pr = int(pr)
        repo = REPOS.get(short, short)
        x = imap.get((repo, pr))
        if not x:
            print(f"not found: {repo}#{pr}", flush=True); continue
        tag = repo.replace("/", "__") + "__" + str(pr)
        clog = os.path.join(OUTDIR, tag + "__calls.jsonl")
        open(clog, "w").close()                 # truncate
        call_log.install(clog)                  # registers the litellm per-call logger ONCE
        from oh_delegate import oh_review_delegate  # import AFTER install so callback is live
        d = str(ensure_repo(repo, base_sha(repo, pr)))
        print(f"=== {repo}#{pr}: delegation with per-call logging -> {clog}", flush=True)
        review, trace = oh_review_delegate(d, x["input"],
                                           trace_path=os.path.join(OUTDIR, tag + "__orch.json"))
        ncalls = sum(1 for _ in open(clog))
        print(f"    done: review {len(review)} chars, orchestrator actions {len(trace)}, "
              f"LLM calls logged {ncalls}", flush=True)


if __name__ == "__main__":
    main()
