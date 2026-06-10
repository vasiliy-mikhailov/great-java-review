"""Per-reviewer vs group-of-5 GEPA, on the HIGH-QUALITY FULL-MR pool.

For each reviewer: GEPA a PERSONAL prompt (k=1).
For each group of 5 reviewers: GEPA ONE SHARED prompt.
Then score each reviewer's held-out high-quality full-MR PRs with:
  baseline (seed) · personal prompt · the prompt shared across its group of 5.

Answers: how much mimicry quality do you lose by sharing a prompt over 5
reviewers instead of personalizing to one? (full MR, quality-gated, think=on)

Usage: python src/group_experiment.py [profile] [budget]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from statistics import mean

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
from gepa_run import (_run_gepa, SEED_PER_REVIEWER, SEED_SINGLE,  # noqa: E402
                      SYS_KEY, leaks_reference)
from compare import eval_prompt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
SEED = CFG["gepa"].get("seed", 7)
PROMPTS = ROOT / "prompts" / "groups"
RESULTS = ROOT / "results"
GROUP = 5
BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 60   # metric calls / GEPA run
MIN_INST = 18                                            # need train+val+test


def _sizes(n):
    te = max(4, min(20, n // 3))
    va = max(2, min(10, n // 5))
    tr = max(4, n - te - va)
    return tr, va, te


def _gepa(seed_text, train, val, tag):
    best = _run_gepa(seed_text, train, val, "qwen", tag, BUDGET).best_candidate[SYS_KEY]
    return seed_text if leaks_reference(best) else best   # never ship a leaky prompt


def run(profile="qwen"):
    sel = CFG["selection"]
    inst = ds.build_instances(quality_gate=sel.get("quality_gate"),
                              quality_threshold=sel.get("quality_threshold", 4))
    logins = sorted([l for l, xs in inst.items() if len(xs) >= MIN_INST],
                    key=lambda l: -len(inst[l]))
    if len(logins) < GROUP:
        print(f"[grp] only {len(logins)} reviewers with >= {MIN_INST} HQ units; "
              "need more judged."); return
    splits = {}
    for l in logins:
        tr, va, te = _sizes(len(inst[l]))
        a, b, c = ds.split3(inst[l], tr, va, te, SEED)
        splits[l] = {"train": a, "val": b, "test": c}
    workers = CFG[profile].get("max_concurrency", 4)
    PROMPTS.mkdir(parents=True, exist_ok=True)
    print(f"[grp] {len(logins)} HQ full-MR reviewers: {logins}  budget={BUDGET}/run")

    # 1) personal prompts ----------------------------------------------------
    per = {}
    for l in logins:
        per[l] = _gepa(SEED_PER_REVIEWER.format(login=l), splits[l]["train"],
                       splits[l]["val"], f"{profile}_grpexp_per_{l}")
        (PROMPTS / f"per_{l}.txt").write_text(per[l])
        print(f"[grp] personal prompt: {l} ({len(per[l])} ch)", flush=True)

    # 2) group-of-5 shared prompts -------------------------------------------
    groups = [logins[i:i + GROUP] for i in range(0, len(logins), GROUP)]
    grp_of = {}
    for gi, grp in enumerate(groups):
        train = [i for l in grp for i in splits[l]["train"]]
        val = [i for l in grp for i in splits[l]["val"]]
        best = _gepa(SEED_SINGLE, train, val, f"{profile}_grpexp_g{gi}")
        (PROMPTS / f"group{gi}.txt").write_text(best)
        for l in grp:
            grp_of[l] = best
        print(f"[grp] group {gi} prompt over {grp} ({len(best)} ch)", flush=True)

    # 3) compare on each reviewer's held-out HQ full-MR test -----------------
    rows = []
    for l in logins:
        test = splits[l]["test"]
        b, _ = eval_prompt(SEED_PER_REVIEWER.format(login=l), test, profile, workers)
        p, _ = eval_prompt(per[l], test, profile, workers)
        g, _ = eval_prompt(grp_of[l], test, profile, workers)
        gi = next(i for i, grp in enumerate(groups) if l in grp)
        rows.append({"reviewer": l, "group": gi, "n_test": len(test),
                     "baseline": round(b, 4), "personal": round(p, 4),
                     "group5": round(g, 4)})
        print(f"[grp] {l:18s} base={b:.3f} personal={p:.3f} group5={g:.3f}", flush=True)
        _save(rows, groups, profile)
    _save(rows, groups, profile, final=True)


def _save(rows, groups, profile, final=False):
    agg = {k: round(mean(r[k] for r in rows), 4)
           for k in ("baseline", "personal", "group5")} if rows else {}
    out = {"profile": profile, "budget": BUDGET, "n_reviewers": len(rows),
           "groups": groups, "aggregate": agg,
           "personal_minus_group5": round(agg.get("personal", 0) - agg.get("group5", 0), 4)
           if agg else None, "rows": rows}
    (RESULTS / f"group_experiment.{profile}.json").write_text(json.dumps(out, indent=2))
    if final and rows:
        L = [f"# Per-reviewer vs group-of-5 ({profile}, HQ full-MR)", "",
             "Mimicry score on each reviewer's held-out high-quality full-MR PRs.",
             "", "| reviewer | grp | n | baseline | personal | group-of-5 |",
             "|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['reviewer']} | {r['group']} | {r['n_test']} | "
                     f"{r['baseline']:.3f} | {r['personal']:.3f} | {r['group5']:.3f} |")
        L += [f"| **MEAN** | | | **{agg['baseline']:.3f}** | "
              f"**{agg['personal']:.3f}** | **{agg['group5']:.3f}** |", "",
              "## Takeaway", "",
              f"- personal vs baseline: {agg['personal']-agg['baseline']:+.4f}",
              f"- personal vs group-of-5: {agg['personal']-agg['group5']:+.4f} "
              "(positive ⇒ personalization beats sharing across 5)"]
        (RESULTS / f"group_experiment.{profile}.md").write_text("\n".join(L))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "qwen")
