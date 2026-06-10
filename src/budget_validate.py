"""Validate the improved harness on the BIGGEST PR (quarkus#53917): full 240k-char
subagent context + 32k subagent output cap. Confirms it completes, produces a real
review, and hits NO context/budget errors (prompt+output <= 262k).

  ./venv-oh/bin/python -u src/budget_validate.py
"""
from __future__ import annotations
import os, sys, time, warnings, traceback
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from oh_delegate import oh_review_delegate  # noqa: E402


def main():
    inst = ds.build_instances()
    x = next(v for vs in inst.values() for v in vs
             if v["repo"] == "quarkusio/quarkus" and str(v["pr"]) == "53917")
    sha = base_sha(x["repo"], x["pr"]); d = ensure_repo(x["repo"], sha)
    print(f"validating biggest PR {x['repo']}#{x['pr']} (full subagent ctx + 32k out)…", flush=True)
    t0 = time.time()
    try:
        review, trace = oh_review_delegate(str(d), x["input"])
        dt = time.time() - t0
        score, _ = mt.score_with_feedback(x["input"], review, x["reference_review"])
        n_deleg = sum(1 for t, _ in trace if t.startswith("task"))
        print(f"\n=== VALIDATION ===", flush=True)
        print(f"completed in {dt:.0f}s | review_len={len(review.strip())} "
              f"has_SUMMARY={'SUMMARY:' in review} has_POINTS={'POINTS:' in review}", flush=True)
        print(f"score={score:.3f} | delegations={n_deleg} | orch_actions={len(trace)}", flush=True)
        print(f"trace: {[t for t,_ in trace]}", flush=True)
        print(f"\n--- REVIEW ---\n{review[:1400]}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"\n=== FAILED: {type(e).__name__}: {e} ===", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    main()
