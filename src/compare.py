"""Compare review-mimicry prompts on a held-out test set.

For each chosen reviewer we score, on PRs unseen during optimization:
  baseline  : the generic seed prompt
  per_review: the GEPA-optimized per-reviewer prompt
  single    : the GEPA-optimized single universal prompt

Writes results/comparison.json and results/comparison.md.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from gepa_run import (SEED_PER_REVIEWER, SEED_SINGLE, generate,  # noqa: E402
                      adaptive_sizes)

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
G = CFG["gepa"]
PROMPTS = ROOT / "prompts"
RESULTS = ROOT / "results"


def eval_prompt(prompt_text, testset, profile, workers):
    def one(inst):
        out = generate(prompt_text, inst["input"], profile)
        sc, _ = mt.score_with_feedback(inst["input"], out,
                                       inst["reference_review"], profile)
        return sc
    with ThreadPoolExecutor(max_workers=workers) as ex:
        scores = list(ex.map(one, testset))
    return mean(scores) if scores else 0.0, scores


def compare(profile="qwen"):
    inst = ds.build_instances()
    workers = CFG[profile].get("max_concurrency", 4)
    single_path = PROMPTS / f"single_great.{profile}.txt"
    single_prompt = single_path.read_text() if single_path.exists() else SEED_SINGLE

    rows = []
    for login, xs in inst.items():
        per_path = PROMPTS / "per_reviewer" / f"{login}.{profile}.txt"
        if not per_path.exists():
            continue
        tr_n, va_n, te_n = adaptive_sizes(len(xs))
        _, _, test = ds.split3(xs, tr_n, va_n, te_n, G.get("seed", 7))
        if not test:
            continue
        per_prompt = per_path.read_text()
        base = SEED_PER_REVIEWER.format(login=login)
        b, _ = eval_prompt(base, test, profile, workers)
        p, _ = eval_prompt(per_prompt, test, profile, workers)
        s, _ = eval_prompt(single_prompt, test, profile, workers)
        row = {"reviewer": login, "n_test": len(test),
               "baseline": round(b, 4), "per_reviewer": round(p, 4),
               "single_great": round(s, 4)}
        rows.append(row)
        print(f"{login:22s} base={b:.3f} per={p:.3f} single={s:.3f}")
        (RESULTS / "comparison.json").write_text(json.dumps(rows, indent=2))

    if rows:
        agg = {k: round(mean(r[k] for r in rows), 4)
               for k in ("baseline", "per_reviewer", "single_great")}
        out = {"profile": profile, "per_reviewer_rows": rows, "aggregate": agg}
        (RESULTS / "comparison.json").write_text(json.dumps(out, indent=2))
        _write_md(out)
        print("\nAGGREGATE:", agg)


def _write_md(out):
    rows = out["per_reviewer_rows"]
    agg = out["aggregate"]
    lines = [f"# Prompt comparison ({out['profile']})", "",
             "Mean review-mimicry score on held-out PRs (higher = closer to the "
             "real reviewer). Metric = 0.85·LLM-judge + 0.15·lexical.", "",
             "| Reviewer | n | baseline | per-reviewer GEPA | single GEPA |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['reviewer']} | {r['n_test']} | {r['baseline']:.3f} "
                     f"| {r['per_reviewer']:.3f} | {r['single_great']:.3f} |")
    lines += ["", f"| **MEAN** |  | **{agg['baseline']:.3f}** | "
              f"**{agg['per_reviewer']:.3f}** | **{agg['single_great']:.3f}** |",
              "",
              "## Takeaway", "",
              f"- Per-reviewer GEPA vs baseline: "
              f"{agg['per_reviewer']-agg['baseline']:+.3f}",
              f"- Single universal GEPA vs baseline: "
              f"{agg['single_great']-agg['baseline']:+.3f}",
              f"- Per-reviewer vs single: "
              f"{agg['per_reviewer']-agg['single_great']:+.3f} "
              "(positive = personalization helps)"]
    (RESULTS / "comparison.md").write_text("\n".join(lines))


if __name__ == "__main__":
    compare(sys.argv[1] if len(sys.argv) > 1 else "qwen")
