"""Fibonacci scaling sweep for the single *universal* GEPA review prompt.

Question: how well can ONE universal prompt mimic the FIRST k reviewers, on
held-out PRs of *those same k reviewers*?  k sweeps Fibonacci (1, 2, 3, 5, 8,
..., up to max_k), capped at the number of usable reviewers.

IN-DOMAIN evaluation (the point of the experiment):
  * Each reviewer's instances are split into train / val / test.
  * For k, the prompt is GEPA-optimized on the pooled train of the first k
    reviewers, selected on their pooled val, and SCORED on their pooled test.
  * So the prompt only has to generalize to the k reviewers we actually have
    (k=1 -> mimic one reviewer on their unseen PRs; k=2 -> two; ...), NOT to the
    whole population. Lower k = easier (be one voice); higher k = one prompt must
    satisfy more distinct voices at once.

Bounded cost: val/test pools are round-robin sampled to val_cap/eval_cap across
the k reviewers (so every reviewer is represented and GEPA cost stays flat), and
the GEPA budget grows only mildly with k (log, capped).

Reviewers are added best-covered-first (deterministic) -> k=1 ⊂ k=2 ⊂ ...

Output: results/fib_sweep.<profile>.<eval_mode>.json and .md. Resumable per-k.

Usage: python src/fib_sweep.py [profile]
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import wide_dataset as wds  # noqa: E402
from gepa_run import _run_gepa, SEED_SINGLE, SYS_KEY  # noqa: E402
from compare import eval_prompt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
FS = CFG["fib_sweep"]
SEED = CFG["gepa"].get("seed", 7)
PROMPTS = ROOT / "prompts" / "fib"
RESULTS = ROOT / "results"


def fibs_upto(n: int) -> list[int]:
    seq, a, b = [], 1, 2
    while a <= n:
        if a not in seq:
            seq.append(a)
        a, b = b, a + b
    return seq


def load_pool():
    if FS.get("source", "wide") == "deep":
        return ds.build_instances()
    sel = CFG.get("selection", {})
    return wds.build_wide_instances(
        FS.get("min_ref_chars", 80),
        quality_gate=sel.get("quality_gate"),
        quality_threshold=sel.get("quality_threshold", 4))


def per_reviewer_splits(inst):
    """Per-reviewer train/val/test splits (held-out test = in-domain eval)."""
    tp, vp, ep = (FS["train_per_reviewer"], FS["val_per_reviewer"],
                  FS["test_per_reviewer"])
    min_n = FS["min_instances"]
    splits = {}
    for login, xs in inst.items():
        n = len(xs)
        if n < min_n:
            continue
        te = max(2, min(ep, n // 4))
        va = max(2, min(vp, n // 5))
        tr = n - te - va
        if tr < 2:
            continue
        tr = min(tr, tp)
        a, b, c = ds.split3(xs, tr, va, te, SEED)
        if a and b and c:
            splits[login] = {"train": a, "val": b, "test": c}
    return splits


def round_robin(lists, cap):
    """Take items one-per-reviewer in rounds -> balanced coverage up to cap."""
    pools = [list(x) for x in lists]
    for p in pools:
        random.Random(SEED).shuffle(p)
    out = []
    while len(out) < cap:
        progressed = False
        for p in pools:
            if p:
                out.append(p.pop())
                progressed = True
                if len(out) >= cap:
                    break
        if not progressed:
            break
    return out


def budget(k: int) -> int:
    base = FS["base_metric_calls"]
    m = base * (1 + FS["budget_log_alpha"] * math.log2(max(2, k)))
    return int(min(m, base * FS["budget_cap_mult"]))


def run(profile: str = "qwen", trial=None):
    mode = FS.get("eval_mode", "in_domain")
    cfg = None
    suffix = ""
    if trial is not None:
        from build_prompts import load_config, gepa_with_cfg  # noqa: E402
        cfg = load_config(trial)
        suffix = f".t{trial}"
        AT = CFG["autoresearch"]
        gepa_secs = AT.get("gepa_seconds", 300)
        patience = AT.get("no_improve_patience", 2)
        print(f"[fib] using AutoResearch config t{trial}: {cfg}")
    if CFG.get("selection", {}).get("quality_gate") == "qwen":
        suffix += ".hq"            # high-quality (qwen-gated) pool -> separate outputs
    inst = load_pool()
    if not inst:
        print("[fib] empty pool (run discovery/wide crawl first)"); return
    splits = per_reviewer_splits(inst)
    logins = sorted(splits, key=lambda l: (-len(inst[l]), l))
    n = len(logins)
    if n == 0:
        print(f"[fib] no reviewers with >= {FS['min_instances']} instances yet")
        return
    max_k = min(FS["max_k"], n)
    ks = fibs_upto(max_k)
    if FS.get("include_all_point") and n not in ks:
        ks.append(n)
    workers = CFG[profile].get("max_concurrency", 4)
    PROMPTS.mkdir(parents=True, exist_ok=True)
    print(f"[fib] mode={mode} usable_reviewers={n} (>= {FS['min_instances']} inst) "
          f"source={FS.get('source','wide')}")
    print(f"[fib] sweeping k={ks}  val_cap={FS['val_cap']}  eval_cap={FS['eval_cap']}")

    out_path = RESULTS / f"fib_sweep.{profile}.{mode}{suffix}.json"
    prev = json.loads(out_path.read_text()) if out_path.exists() else {}
    done = {p["k"]: p for p in prev.get("points", [])}

    rows, out = [], {}
    for k in ks:
        subset = logins[:k]
        if k in done and (PROMPTS / f"single_k{k}.{profile}.{mode}{suffix}.txt").exists():
            rows.append(done[k])
            print(f"[fib] k={k}: cached eval={done[k]['eval_score']}")
        else:
            train = [i for lo in subset for i in splits[lo]["train"]]
            val = round_robin([splits[lo]["val"] for lo in subset], FS["val_cap"])
            ev = round_robin([splits[lo]["test"] for lo in subset], FS["eval_cap"])
            tag = f"{profile}_fib_{mode}{suffix}_k{k}"
            if cfg is not None:                         # AutoResearch t-config
                best = gepa_with_cfg(SEED_SINGLE, train, val, cfg, profile,
                                     tag, gepa_secs, patience)
                bud = f"{gepa_secs}s"
            else:                                       # default metric-call budget
                mc = budget(k)
                best = _run_gepa(SEED_SINGLE, train, val, profile, tag,
                                 mc).best_candidate[SYS_KEY]
                bud = mc
            (PROMPTS / f"single_k{k}.{profile}.{mode}{suffix}.txt").write_text(best)
            score, _ = eval_prompt(best, ev, profile, workers)
            row = {"k": k, "n_train": len(train), "n_val": len(val),
                   "n_eval": len(ev), "metric_budget": bud,
                   "eval_score": round(score, 4), "example_reviewers": subset[:8]}
            rows.append(row)
            print(f"[fib] k={k:5d}  train={len(train):5d}  eval={len(ev):3d}  "
                  f"budget={bud}  in-domain eval={score:.4f}")
        out = {"profile": profile, "eval_mode": mode, "config_trial": trial,
               "order": "best_covered_first", "source": FS.get("source", "wide"),
               "n_usable_reviewers": n, "ks": ks, "points": rows}
        out_path.write_text(json.dumps(out, indent=2))
    _write_md(out, profile, mode)
    print(f"[fib] wrote {out_path} and .md")


def _bar(score, lo, hi, width=34):
    if hi <= lo:
        return "#" * (width // 2)
    return "#" * max(1, int(round((score - lo) / (hi - lo) * width)))


def _write_md(out, profile, mode):
    rows = out.get("points", [])
    if not rows:
        return
    vals = [r["eval_score"] for r in rows]
    lo, hi = min(vals), max(vals)
    lines = [f"# Fibonacci scaling sweep — universal prompt ({profile}, {mode})",
             "",
             "How well ONE universal GEPA prompt mimics the first `k` reviewers, "
             "scored on **held-out PRs of those same k reviewers** (in-domain). "
             "k follows Fibonacci. The prompt only has to generalize to the "
             "reviewers we actually have, not the population.", "",
             "| k (reviewers) | train | eval PRs | budget | in-domain score | curve |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['k']} | {r.get('n_train','?')} | {r.get('n_eval','?')} "
                     f"| {r.get('metric_budget','?')} | {r['eval_score']:.4f} | "
                     f"`{_bar(r['eval_score'], lo, hi)}` |")
    best = max(rows, key=lambda r: r["eval_score"])
    lines += ["",
              "## Takeaway", "",
              f"- k=1 (mimic one reviewer): **{rows[0]['eval_score']:.4f}**.",
              f"- k={rows[-1]['k']} (one prompt for all of them): "
              f"**{rows[-1]['eval_score']:.4f}**.",
              f"- Best at k={best['k']} ({best['eval_score']:.4f}).",
              "- A FALLING curve ⇒ one prompt can mimic a single reviewer well but "
              "degrades as it must satisfy more distinct voices at once — i.e. "
              "personalization (per-reviewer prompts) is needed. A FLAT/RISING "
              "curve ⇒ the reviewers are stylistically compatible and a single "
              "prompt captures them all."]
    (RESULTS / f"fib_sweep.{profile}.{mode}.md").write_text("\n".join(lines))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "qwen",
        sys.argv[2] if len(sys.argv) > 2 else None)
