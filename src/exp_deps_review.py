"""Experiment: does giving the reviewer DEPENDENCY SOURCES (+ a verify-before-asserting
hint) kill the dependency-level fabrication and raise review quality?

Re-reviews spring-boot#50273 with spring-framework 6.2.18 sources staged under
deps_src/ in the repo, and a hint to grep them before claiming library behavior.
Compare the resulting review to the earlier (no-deps) MR+code that fabricated
`releaseTarget` throwing.

  ./venv-oh/bin/python -u src/exp_deps_review.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from oh_delegate import oh_review_delegate  # noqa: E402

DEPS_HINT = (
    "\n\n=== DEPENDENCY SOURCES AVAILABLE (use them!) ===\n"
    "This project's dependency sources are checked out under `deps_src/` "
    "(spring-framework 6.2.18: spring-aop, spring-beans, spring-core, spring-context). "
    "BEFORE asserting how ANY framework/library class behaves (e.g. whether a Spring "
    "method throws, returns null, or is a no-op), grep/read its ACTUAL source under "
    "`deps_src/` and ground the claim in what you read. Do NOT guess library internals — "
    "if you cannot verify a library-behavior claim from the source, do not make it.")


def main():
    inst = ds.build_instances()
    x = next(v for vs in inst.values() for v in vs
             if v["repo"] == "spring-projects/spring-boot" and str(v["pr"]) == "50273")
    sha = base_sha(x["repo"], x["pr"]); d = ensure_repo(x["repo"], sha)
    pr_input, human = x["input"], x["reference_review"]
    review, trace = "", []
    for attempt in range(4):   # retry on empty/stalled rollout
        print(f"=== MR+code WITH deps_src, attempt {attempt + 1} …", flush=True)
        review, trace = oh_review_delegate(str(d), pr_input + DEPS_HINT)
        if len(review.strip()) >= 200:
            print(f"    got real review (len {len(review)})", flush=True)
            break
        print(f"    stalled (len {len(review.strip())}) — retry", flush=True)
    score, _ = mt.score_with_feedback(pr_input, review, human)
    json.dump({"repo": x["repo"], "pr": 50273, "human": human, "pr_input": pr_input,
               "mr_code_deps": review, "mr_code_deps_score": round(score, 4),
               "trace": [t for t, _ in trace]},
              open("results/qual_deps_spring50273.json", "w"), indent=2)
    print(f"=== DONE: score={score:.3f} ({len(trace)} orch actions) ===", flush=True)
    print("REVIEW:\n" + review, flush=True)


if __name__ == "__main__":
    main()
