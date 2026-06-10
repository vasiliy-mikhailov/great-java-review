"""Build the deep-track prompts using a chosen AutoResearch config (e.g. t34).

Runs per-reviewer GEPA for every reviewer in excellent_reviews.json AND the
single universal prompt, all under one fixed hyperparameter config drawn from a
tuning trial, so the resulting prompt set is internally consistent and reflects
the tuned regime (not the stale defaults).

Usage:
  python src/build_prompts.py [profile] [trial]   # trial: int (e.g. 34) or 'best'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import gepa  # noqa: E402
from gepa import TimeoutStopCondition, NoImprovementStopper, CompositeStopper  # noqa: E402

import dataset as ds  # noqa: E402
from gepa_run import (SEED_PER_REVIEWER, SEED_SINGLE, SYS_KEY,  # noqa: E402
                      leaks_reference)
from autoresearch import TunableAdapter, _reflection_lm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
AT = CFG["autoresearch"]
PROMPTS = ROOT / "prompts"
RESULTS = ROOT / "results"
(PROMPTS / "per_reviewer").mkdir(parents=True, exist_ok=True)


def load_config(trial):
    rows = [json.loads(x) for x in (RESULTS / "autoresearch.jsonl").read_text()
            .splitlines() if x.strip()]
    if trial == "best":
        return max(rows, key=lambda r: r["score"])["config"]
    return next(r for r in rows if r["trial"] == int(trial))["config"]


def gepa_with_cfg(seed_text, train, val, cfg, profile, tag, gepa_secs, patience):
    workers = CFG[profile].get("max_concurrency", 4)
    adapter = TunableAdapter(profile, workers, cfg["gen_max_tokens"],
                             cfg["gen_temperature"])
    run_dir = str(RESULTS / "runs" / tag)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    stopper = CompositeStopper(TimeoutStopCondition(gepa_secs),
                               NoImprovementStopper(patience), mode="any")
    res = gepa.optimize(
        seed_candidate={SYS_KEY: seed_text}, trainset=train, valset=val,
        adapter=adapter,
        reflection_lm=_reflection_lm(profile, cfg["reflect_think"]),
        reflection_minibatch_size=cfg["reflect_minibatch"],
        candidate_selection_strategy=cfg["sel_strategy"],
        max_metric_calls=100000, stop_callbacks=[stopper],
        seed=cfg["gepa_seed"], run_dir=run_dir,
        display_progress_bar=False, raise_on_exception=False,
    )
    best = res.best_candidate[SYS_KEY]
    if leaks_reference(best):     # never ship a leaky prompt; clean seed is the floor
        print(f"[build]   ! {tag}: best candidate leaked reference -> using seed")
        best = seed_text
    return best


def run(profile="qwen", trial="34"):
    cfg = load_config(trial)
    gepa_secs = AT.get("gepa_seconds", 300)
    patience = AT.get("no_improve_patience", 2)
    seed = CFG["gepa"].get("seed", 7)
    tpr, vpr = cfg["train_per_reviewer"], cfg["val_size"]
    print(f"[build] config from trial {trial}: {cfg}")

    inst = ds.build_instances()
    logins = sorted(inst, key=lambda l: -len(inst[l]))
    summary = []

    # 1) per-reviewer prompts -------------------------------------------------
    for login in logins:
        xs = inst[login]
        if len(xs) < 8:
            print(f"[build] skip {login} ({len(xs)} inst)"); continue
        out = PROMPTS / "per_reviewer" / f"{login}.{profile}.txt"
        if out.exists() and not leaks_reference(out.read_text()):
            print(f"[build] keep {login} (clean prompt already on disk)")
            summary.append({"login": login, "prompt_chars": len(out.read_text())})
            continue
        tr_n = min(tpr, max(4, len(xs) - 6))
        va_n = min(vpr, max(2, len(xs) - tr_n - 2))
        tr, va = ds.split(xs, tr_n, va_n, seed)
        seed_text = SEED_PER_REVIEWER.format(login=login)
        print(f"[build] per-reviewer {login}: n={len(xs)} train={len(tr)} val={len(va)}",
              flush=True)
        best = gepa_with_cfg(seed_text, tr, va, cfg, profile,
                             f"{profile}_t{trial}_{login}", gepa_secs, patience)
        out = PROMPTS / "per_reviewer" / f"{login}.{profile}.txt"
        out.write_text(best)
        summary.append({"login": login, "prompt_chars": len(best)})
        print(f"[build]   -> {out} ({len(best)} chars)", flush=True)

    # 2) single universal prompt ---------------------------------------------
    tr, va = [], []
    per = max(2, tpr // max(1, len(logins)))
    pv = max(1, vpr // max(1, len(logins)))
    for login in logins:
        a, b = ds.split(inst[login], per, pv, seed)
        tr += a; va += b
    sp = PROMPTS / f"single_great.{profile}.txt"
    if sp.exists() and not leaks_reference(sp.read_text()):
        print("[build] keep single (clean prompt already on disk)")
        best = sp.read_text()
    else:
        print(f"[build] single universal: train={len(tr)} val={len(va)}", flush=True)
        best = gepa_with_cfg(SEED_SINGLE, tr, va, cfg, profile,
                             f"{profile}_t{trial}_single", gepa_secs, patience)
        sp.write_text(best)
        print(f"[build]   -> single_great.{profile}.txt ({len(best)} chars)", flush=True)

    (RESULTS / f"build_prompts_t{trial}.{profile}.json").write_text(
        json.dumps({"trial": trial, "config": cfg, "per_reviewer": summary,
                    "single_chars": len(best)}, indent=2))
    print(f"[build] DONE. {len(summary)} per-reviewer prompts + 1 universal.")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "qwen",
        sys.argv[2] if len(sys.argv) > 2 else "34")
