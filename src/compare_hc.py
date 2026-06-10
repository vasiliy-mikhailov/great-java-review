"""Higher-confidence comparison: baseline vs per-reviewer vs single.

Variance reduction vs compare.py:
  * Larger held-out test (test_n PRs, default 60) instead of ~12.
  * Test set is the reviewer's instances OUTSIDE the prompt's training split
    (same seed-7 shuffle, reserve the first 50 = the train(20)+val(30) used by
    build_prompts) -> strictly disjoint, no leakage.
  * Deterministic generation (temp=0) -> removes generation noise entirely, so
    the only remaining variance is which held-out PRs were sampled.

Writes results/comparison_hc.json / .md.

Usage: python src/compare_hc.py [profile]
"""
from __future__ import annotations

import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from gepa_run import SEED_PER_REVIEWER  # noqa: E402
from autoresearch import _gen  # noqa: E402
from llm_client import get_llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
PROMPTS = ROOT / "prompts"
RESULTS = ROOT / "results"
SEED = CFG["gepa"].get("seed", 7)
RESERVE = 50          # train(20)+val(30) used by build_prompts -> excluded from test
TEST_N = 60           # held-out PRs per reviewer
GEN_MAX_TOK = 1600    # >= saturation (cap is non-binding for these reviewers)


def held_out(xs):
    idx = list(range(len(xs)))
    random.Random(SEED).shuffle(idx)
    pool = [xs[i] for i in idx[RESERVE:]]   # strictly outside train+val
    return pool[:TEST_N]


def run(profile="qwen"):
    workers = CFG[profile].get("max_concurrency", 4)
    llm = get_llm(profile)
    sel = CFG.get("selection", {})
    inst = ds.build_instances(quality_gate=sel.get("quality_gate"),
                              quality_threshold=sel.get("quality_threshold", 4))
    single_path = PROMPTS / f"single_great.{profile}.txt"
    single_prompt = single_path.read_text()

    def score_prompt(prompt, test):
        def one(i):
            out = _gen(llm, prompt, i["input"], GEN_MAX_TOK, 0.0)   # temp=0
            sc, _ = mt.score_with_feedback(i["input"], out, i["reference_review"],
                                           profile)
            return sc
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return mean(list(ex.map(one, test)))

    rows = []
    for login, xs in sorted(inst.items(), key=lambda kv: -len(kv[1])):
        per_path = PROMPTS / "per_reviewer" / f"{login}.{profile}.txt"
        if not per_path.exists():
            continue
        test = held_out(xs)
        if len(test) < 6:
            print(f"skip {login}: only {len(test)} held-out"); continue
        base = SEED_PER_REVIEWER.format(login=login)
        b = score_prompt(base, test)
        p = score_prompt(per_path.read_text(), test)
        s = score_prompt(single_prompt, test)
        row = {"reviewer": login, "n_test": len(test),
               "baseline": round(b, 4), "per_reviewer": round(p, 4),
               "single_great": round(s, 4)}
        rows.append(row)
        print(f"{login:18s} n={len(test):3d} base={b:.3f} per={p:.3f} "
              f"single={s:.3f}", flush=True)
        _save(rows, profile)
    _save(rows, profile, final=True)


def _save(rows, profile, final=False):
    agg = {k: round(mean(r[k] for r in rows), 4)
           for k in ("baseline", "per_reviewer", "single_great")} if rows else {}
    wins = {"per_over_base": sum(r["per_reviewer"] > r["baseline"] for r in rows),
            "per_over_single": sum(r["per_reviewer"] > r["single_great"] for r in rows)}
    out = {"profile": profile, "test_n": TEST_N, "temp": 0.0, "reserve": RESERVE,
           "aggregate": agg, "wins": wins, "n_reviewers": len(rows),
           "per_reviewer_rows": rows}
    (RESULTS / "comparison_hc.json").write_text(json.dumps(out, indent=2))
    if final:
        _md(out)


def _md(out):
    rows = out["per_reviewer_rows"]; agg = out["aggregate"]
    L = [f"# High-confidence prompt comparison ({out['profile']})", "",
         f"Held-out test = {out['test_n']} PRs/reviewer (disjoint from training), "
         "deterministic temp=0 generation. Mean review-mimicry score "
         "(0.85·judge + 0.15·lexical).", "",
         "| Reviewer | n | baseline | per-reviewer | single |",
         "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['reviewer']} | {r['n_test']} | {r['baseline']:.3f} | "
                 f"{r['per_reviewer']:.3f} | {r['single_great']:.3f} |")
    L += [f"| **MEAN** |  | **{agg['baseline']:.3f}** | "
          f"**{agg['per_reviewer']:.3f}** | **{agg['single_great']:.3f}** |", "",
          "## Takeaway", "",
          f"- per-reviewer vs baseline: {agg['per_reviewer']-agg['baseline']:+.4f} "
          f"({out['wins']['per_over_base']}/{out['n_reviewers']} reviewers win)",
          f"- single vs baseline: {agg['single_great']-agg['baseline']:+.4f}",
          f"- per-reviewer vs single: {agg['per_reviewer']-agg['single_great']:+.4f} "
          f"({out['wins']['per_over_single']}/{out['n_reviewers']} reviewers win)"]
    (RESULTS / "comparison_hc.md").write_text("\n".join(L))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "qwen")
