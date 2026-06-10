"""Matched before/after: diff-only (no repo) vs the GEPA-EVOLVED agent policy,
on the SAME PRs as agent_poc_batch. 3 of the 5 reviewers were NOT in GEPA's
training set (romani, mkouba, SaptarshiSarkar12) -> a true generalization test.

Answers: "what is the similarity before the harness could read code, vs after
(with the optimized policy)?"

Usage: python src/eval_evolved_policy.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, os.path.dirname(__file__))
import metric as mt  # noqa: E402
from agent_review import diff_only_review, agent_review  # noqa: E402
from agent_poc_batch import pick, base_sha, ensure_repo  # noqa: E402

POLICY = Path("prompts/agent_policy.qwen.txt").read_text()


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
        do = diff_only_review(x["input"])
        ds_s, _ = mt.score_with_feedback(x["input"], do, x["reference_review"])
        ar, trace = agent_review(d, x["input"], policy=POLICY)   # EVOLVED policy
        ar_s, _ = mt.score_with_feedback(x["input"], ar, x["reference_review"])
        rows.append({"repo": repo, "pr": pr, "reviewer": login,
                     "diff_only": round(ds_s, 4), "agent_repo": round(ar_s, 4),
                     "delta": round(ar_s - ds_s, 4), "tool_calls": len(trace),
                     "tools": [t for t, _ in trace]})
        print(f"  diff-only {ds_s:.3f}  evolved-agent {ar_s:.3f}  Δ {ar_s-ds_s:+.3f}  "
              f"({len(trace)} tools)", flush=True)
        Path("results/evolved_vs_diffonly.json").write_text(json.dumps({"rows": rows}, indent=2))
    if rows:
        agg = {"diff_only": round(mean(r["diff_only"] for r in rows), 4),
               "agent_repo": round(mean(r["agent_repo"] for r in rows), 4),
               "mean_delta": round(mean(r["delta"] for r in rows), 4),
               "n": len(rows), "agent_wins": sum(r["delta"] > 0 for r in rows)}
        Path("results/evolved_vs_diffonly.json").write_text(json.dumps(
            {"aggregate": agg, "rows": rows}, indent=2))
        print(f"\n=== AGGREGATE ({agg['n']}): before(diff-only) {agg['diff_only']} -> "
              f"after(evolved-agent) {agg['agent_repo']}  (mean Δ {agg['mean_delta']:+.3f}, "
              f"wins {agg['agent_wins']}/{agg['n']}) ===", flush=True)


if __name__ == "__main__":
    run()
