"""Capture the FULL review text from both the seed policy and the evolved policy
on one PR, for a qualitative point-by-point comparison vs the human review.

Usage: python src/capture_reviews.py <repo> <pr>
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_review import agent_review, diff_only_review, SYS  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402

EVOLVED = Path("prompts/agent_policy.qwen.txt").read_text()


def run(repo, pr):
    inst = ds.build_instances()
    x = next(v for L in inst.values() for v in L
             if v["repo"] == repo and str(v["pr"]) == str(pr))
    sha = base_sha(repo, pr)
    d = ensure_repo(repo, sha)
    out = {"repo": repo, "pr": pr, "reviewer": x["reviewer"],
           "human": x["reference_review"]}

    print("=== DIFF-ONLY (no repo) ===", flush=True)
    do = diff_only_review(x["input"])
    do_s, _ = mt.score_with_feedback(x["input"], do, x["reference_review"])
    out["diff_only"] = {"review": do, "score": round(do_s, 4)}
    print(do, f"\n[score {do_s:.3f}]\n", flush=True)

    print("=== SEED policy (agent) ===", flush=True)
    sr, st = agent_review(d, x["input"], policy=SYS)
    sr_s, _ = mt.score_with_feedback(x["input"], sr, x["reference_review"])
    out["seed_agent"] = {"review": sr, "score": round(sr_s, 4),
                         "tools": [t for t, _ in st]}
    print(sr, f"\n[score {sr_s:.3f}, {len(st)} tools]\n", flush=True)

    print("=== EVOLVED policy (agent) ===", flush=True)
    er, et = agent_review(d, x["input"], policy=EVOLVED)
    er_s, _ = mt.score_with_feedback(x["input"], er, x["reference_review"])
    out["evolved_agent"] = {"review": er, "score": round(er_s, 4),
                            "tools": [t for t, _ in et]}
    print(er, f"\n[score {er_s:.3f}, {len(et)} tools]\n", flush=True)

    Path("results").mkdir(exist_ok=True)
    Path(f"results/capture_{repo.replace('/','_')}_{pr}.json").write_text(
        json.dumps(out, indent=2))
    print(f"saved results/capture_{repo.replace('/','_')}_{pr}.json", flush=True)


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]))
