"""5-PR baseline for the OpenHands DELEGATION reviewer (Attempt 3).

Runs the orchestrator+code-explorer-subagent reviewer on the same 5 PRs as the
home-grown batch, so we can compare delegation-seed vs diff-only vs home-grown.
This is the BASELINE the GEPA-optimized orchestrator prompt must beat.

  ./venv-oh/bin/python src/oh_delegate_batch.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from statistics import mean

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

sys.path.insert(0, os.path.dirname(__file__))
import metric as mt  # noqa: E402
from agent_poc_batch import pick, base_sha, ensure_repo  # noqa: E402
from oh_delegate import oh_review_delegate  # noqa: E402


def run():
    chosen, imap = pick()
    print("targets:", [(r, p, l) for r, p, l in chosen], flush=True)
    rows = []
    for repo, pr, login in chosen:
        x = imap[(repo, str(pr))]
        sha = base_sha(repo, pr)
        print(f"\n=== {repo}#{pr} ({login}) base={sha[:10]} ===", flush=True)
        d = ensure_repo(repo, sha)
        if d is None:
            print("  clone/checkout failed, skip"); continue
        review, trace = oh_review_delegate(str(d), x["input"])
        score, _ = mt.score_with_feedback(x["input"], review, x["reference_review"])
        n_deleg = sum(1 for t, _ in trace if t.startswith("task"))
        rows.append({"repo": repo, "pr": pr, "reviewer": login,
                     "delegation_score": round(score, 4),
                     "orch_actions": len(trace), "delegations": n_deleg})
        print(f"  delegation score {score:.3f}  ({len(trace)} orch actions, "
              f"{n_deleg} delegations)", flush=True)
        Path("results/oh_delegate_batch.json").write_text(json.dumps({"rows": rows}, indent=2))
    if rows:
        agg = {"delegation_mean": round(mean(r["delegation_score"] for r in rows), 4),
               "n": len(rows)}
        Path("results/oh_delegate_batch.json").write_text(json.dumps(
            {"aggregate": agg, "rows": rows}, indent=2))
        print(f"\n=== AGGREGATE ({agg['n']}): delegation mean {agg['delegation_mean']} ===",
              flush=True)


if __name__ == "__main__":
    run()
