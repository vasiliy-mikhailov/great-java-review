"""GEPA reflective optimization of Java-review prompts against Qwen.

Two entry points:
  per-reviewer : evolve a prompt that mimics ONE reviewer's style + concerns.
  single       : evolve ONE universal prompt across all reviewers, then compare.

The task model and the reflection model are both the Qwen endpoint (Qwen-only
per the chosen plan); everything is model-agnostic via config profiles.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import gepa  # noqa: E402
from gepa import EvaluationBatch, GEPAAdapter  # noqa: E402

import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from llm_client import get_llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
GCFG = CFG["gepa"]
PROMPTS = ROOT / "prompts"
RESULTS = ROOT / "results"
(PROMPTS / "per_reviewer").mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

SYS_KEY = "review_prompt"

# Leakage guard: an optimized prompt must be SELF-CONTAINED. The reference review
# is the held-out target, never an input at inference. A prompt that tells the
# model it is "given a reference review" cheats during optimization and is broken
# in deployment, so we detect and penalize it (GEPA then selects against it).
import re  # noqa: E402
LEAK_RE = re.compile(r"reference\s+review", re.I)
LEAK_PENALTY = 0.3


def leaks_reference(prompt_text: str) -> bool:
    return bool(LEAK_RE.search(prompt_text or ""))

SEED_PER_REVIEWER = """You are imitating the GitHub code reviewer "{login}", an expert Java reviewer.
You are given a pull request (title, description, changed files, and diff).
Write a code review in the exact voice and priorities of {login}.

Output format:
SUMMARY:
<one short paragraph: overall take and the most important concern>
POINTS:
- [path/File.java:line] <specific, actionable comment about that location>
- ...

Focus on real Java pain points: correctness, concurrency/thread-safety, resource
leaks, null-handling, API design, error handling, tests, and edge cases. Be
specific to the diff. Do not invent files or lines that are not in the PR."""

SEED_SINGLE = """You are an expert Java code reviewer.
You are given a pull request (title, description, changed files, and diff).
Write a focused, high-signal code review.

Output format:
SUMMARY:
<one short paragraph: overall take and the most important concern>
POINTS:
- [path/File.java:line] <specific, actionable comment about that location>
- ...

Prioritize the pain points that matter most in real Java review: correctness,
concurrency/thread-safety, resource leaks, null-handling, API design, error
handling, tests, and edge cases. Anchor every point to the diff; never invent
files or lines."""


def adaptive_sizes(n: int):
    """Scale train/val/test to however many instances a reviewer actually has."""
    want_tr, want_va, want_te = (GCFG["train_size"], GCFG["val_size"],
                                 GCFG["test_size"])
    total = want_tr + want_va + want_te
    if n >= total:
        return want_tr, want_va, want_te
    # proportional scale-down, keeping at least a few in val/test
    te = max(3, int(n * want_te / total))
    va = max(3, int(n * want_va / total))
    tr = max(4, n - te - va)
    return tr, va, te


def generate(prompt_text: str, pr_input: str, profile: str) -> str:
    llm = get_llm(profile)
    user = ("Review this pull request now.\n\n" + pr_input +
            "\n\nWrite the review in the required format.")
    from llm_client import final_review
    return final_review(llm.complete(prompt_text, user))  # final answer only, not reasoning


class ReviewAdapter(GEPAAdapter):
    def __init__(self, profile: str = "qwen", workers: int = 4):
        self.profile = profile
        self.workers = workers

    def evaluate(self, batch, candidate, capture_traces=False):
        prompt_text = candidate[SYS_KEY]
        leak = leaks_reference(prompt_text)

        def run_one(inst):
            try:
                out = generate(prompt_text, inst["input"], self.profile)
            except Exception as e:  # noqa: BLE001
                return "", 0.0, f"generation-error:{e}"
            score, fb = mt.score_with_feedback(
                inst["input"], out, inst["reference_review"], self.profile)
            return out, score, fb

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            res = list(ex.map(run_one, batch))

        outputs = [r[0] for r in res]
        scores = [r[1] for r in res]
        if leak:                                  # broken-in-deployment -> penalize
            scores = [s * LEAK_PENALTY for s in scores]
        trajectories = None
        if capture_traces:
            note = (" LEAKAGE: this prompt refers to a 'reference review' that is "
                    "NOT available at inference; rewrite it to be self-contained."
                    if leak else "")
            trajectories = [
                {"input": b["input"], "reference": b["reference_review"],
                 "generated": r[0], "score": s, "feedback": r[2] + note,
                 "reviewer": b.get("reviewer"), "pr_url": b.get("pr_url")}
                for b, r, s in zip(batch, res, scores)
            ]
        return EvaluationBatch(outputs=outputs, scores=scores,
                               trajectories=trajectories)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        recs = []
        for tr in (eval_batch.trajectories or []):
            recs.append({
                "Inputs": tr["input"][:2500],
                "Target review to PREDICT (HIDDEN at inference)": tr["reference"][:1800],
                "Generated Outputs": tr["generated"][:1800],
                "Feedback": (f"score={tr['score']:.2f}. {tr['feedback']} Improve the "
                             "prompt so the generated review matches the target "
                             "reviewer's concerns and voice. CRITICAL: the prompt "
                             "must be SELF-CONTAINED — never tell the model it is "
                             "given a 'reference review' or target; that text is "
                             "hidden at inference."),
            })
        return {comp: recs for comp in components_to_update}


def reflection_lm(profile: str = "qwen"):
    llm = get_llm(profile)

    def _call(prompt):
        if isinstance(prompt, list):
            return llm.chat(prompt, temperature=0.7, think=True)  # no cap
        return llm.complete("", prompt, temperature=0.7, think=True)
    return _call


def _run_gepa(seed_text, trainset, valset, profile, tag, max_calls):
    adapter = ReviewAdapter(profile, workers=CFG[profile].get("max_concurrency", 4))
    run_dir = str(RESULTS / "runs" / tag)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    result = gepa.optimize(
        seed_candidate={SYS_KEY: seed_text},
        trainset=trainset,
        valset=valset,
        adapter=adapter,
        reflection_lm=reflection_lm(profile),
        reflection_minibatch_size=GCFG.get("reflection_minibatch", 4),
        max_metric_calls=max_calls,
        candidate_selection_strategy="pareto",
        seed=GCFG.get("seed", 7),
        run_dir=run_dir,
        display_progress_bar=False,
        track_best_outputs=True,
        raise_on_exception=False,
    )
    return result


def run_per_reviewer(login, profile="qwen"):
    inst = ds.build_instances()
    if login not in inst:
        print(f"no instances for {login}"); return None
    n = len(inst[login])
    tr_n, va_n, _ = adaptive_sizes(n)
    tr, va = ds.split(inst[login], tr_n, va_n, GCFG.get("seed", 7))
    if len(tr) < 4 or len(va) < 2:
        print(f"[gepa:{login}] too few instances ({n}); skipping"); return None
    print(f"[gepa:{login}] n={n} train={len(tr)} val={len(va)}")
    seed = SEED_PER_REVIEWER.format(login=login)
    res = _run_gepa(seed, tr, va, profile, f"{profile}_{login}",
                    GCFG["max_metric_calls"])
    best = res.best_candidate[SYS_KEY]
    out = PROMPTS / "per_reviewer" / f"{login}.{profile}.txt"
    out.write_text(best)
    summ = {"login": login, "profile": profile,
            "val_score": getattr(res, "val_aggregate_scores", None),
            "best_prompt_path": str(out)}
    (RESULTS / f"per_reviewer_{login}_{profile}.json").write_text(
        json.dumps(summ, indent=2, default=str))
    print(f"[gepa:{login}] best prompt -> {out}")
    return res


def ordered_logins(inst, limit=None):
    """Reviewers ordered best-covered first (deterministic)."""
    logins = sorted(inst.keys(), key=lambda l: (-len(inst[l]), l))
    return logins[:limit] if limit else logins


def _single_dataset(inst, logins):
    """Pool train/val across the given reviewers, keeping the TOTAL training
    budget ~constant so a Fibonacci sweep varies diversity, not data volume."""
    tr, va = [], []
    per_tr = max(2, GCFG["train_size"] // max(1, len(logins)))
    per_va = max(1, GCFG["val_size"] // max(1, len(logins)))
    for login in logins:
        a, b = ds.split(inst[login], per_tr, per_va, GCFG.get("seed", 7))
        tr += a; va += b
    return tr, va


def optimize_single(logins, profile, tag, max_calls):
    inst = ds.build_instances()
    tr, va = _single_dataset(inst, logins)
    print(f"[gepa:{tag}] {len(logins)} reviewers, train={len(tr)} val={len(va)}")
    res = _run_gepa(SEED_SINGLE, tr, va, profile, tag, max_calls)
    return res.best_candidate[SYS_KEY], res


def run_single(profile="qwen", max_reviewers=10):
    inst = ds.build_instances()
    logins = ordered_logins(inst, max_reviewers)
    best, res = optimize_single(logins, profile, f"{profile}_single",
                                GCFG["max_metric_calls"])
    out = PROMPTS / f"single_great.{profile}.txt"
    out.write_text(best)
    print(f"[gepa:single] best universal prompt -> {out}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["per", "single"])
    ap.add_argument("--login")
    ap.add_argument("--profile", default="qwen")
    a = ap.parse_args()
    if a.mode == "per":
        run_per_reviewer(a.login, a.profile)
    else:
        run_single(a.profile)
