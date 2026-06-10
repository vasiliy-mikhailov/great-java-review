"""Capture human / diff-only / MR+code review TEXTS for a few PRs so a human (Claude)
can judge review quality point-by-point, independent of the metric.

  ./venv-oh/bin/python -u src/capture_quality.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from agent_review import diff_only_review  # noqa: E402
from oh_delegate import oh_review_delegate  # noqa: E402

TARGETS = [("agroal/agroal", 188),                   # MR+code WON BIG (+0.345)
           ("quarkusio/quarkus", 53917)]             # MR+code LOST BIG (0.08)
OUT = "results/qual_capture2.json"


def main():
    inst = ds.build_instances()
    imap = {(x["repo"], str(x["pr"])): x for v in inst.values() for x in v}
    out = []
    for repo, pr in TARGETS:
        x = imap.get((repo, str(pr)))
        if not x:
            print(f"not found: {repo}#{pr}", flush=True); continue
        sha = base_sha(repo, pr); d = ensure_repo(repo, sha)
        pr_input, human = x["input"], x["reference_review"]
        print(f"=== {repo}#{pr} ({x.get('reviewer')}) — diff-only…", flush=True)
        do = diff_only_review(pr_input)
        do_s, _ = mt.score_with_feedback(pr_input, do, human)
        print(f"    diff-only score {do_s:.3f}; MR+code (slow)…", flush=True)
        oc, _ = oh_review_delegate(str(d), pr_input)
        oc_s, _ = mt.score_with_feedback(pr_input, oc, human)
        out.append({"repo": repo, "pr": pr, "reviewer": x.get("reviewer"),
                    "pr_input": pr_input, "human": human,
                    "diff_only": do, "diff_only_score": round(do_s, 4),
                    "mr_code": oc, "mr_code_score": round(oc_s, 4)})
        json.dump(out, open(OUT, "w"), indent=2)
        print(f"    DONE {repo}#{pr}: diff_only={do_s:.3f} mr_code={oc_s:.3f}", flush=True)
    print(f"=== captured {len(out)} PRs -> {OUT} ===", flush=True)


if __name__ == "__main__":
    main()
