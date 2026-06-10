"""Auto-tuner for the review-mimicry pipeline, in the spirit of Karpathy's
AutoResearch (Mar 2026): an agent-in-the-loop optimization loop, NOT blind
random search.

Each TRIAL: propose a TARGETED change informed by the trajectory of past
experiments -> run one GEPA trial capped at a fixed budget (~5 min, for
comparability) that also stops early if its validation trajectory plateaus ->
score the winning prompt on a FIXED held-out eval set with a FIXED metric ->
KEEP if it beats the incumbent baseline, else REVERT. Repeat.

Two ways it watches the trajectory (the point, vs. a fixed budget alone):
  * cross-trial — proposals hill-climb from the incumbent toward the knob values
    that have historically scored best (informed guesses, not random samples).
  * within-trial — `NoImprovementStopper` ends a trial whose val curve has gone
    flat, so a hopeless config doesn't burn the whole budget.

CRITICAL design rule: tune only the QUALITY knobs (GEPA / data / generation).
The MEASUREMENT is held fixed — same eval PRs, same `0.85*judge+0.15*lexical`
metric — so the search cannot cheat by making the metric lenient; it can only
win by producing a prompt whose reviews are genuinely closer to the reviewer's.

Tuned on one well-covered reviewer; validate the winning config on others.

Output (resumable): results/autoresearch.jsonl (every trial w/ rationale),
results/autoresearch_best.json, results/autoresearch_curve.<profile>.png.

Usage: python src/autoresearch.py [profile]
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import gepa  # noqa: E402
from gepa import (EvaluationBatch, GEPAAdapter, TimeoutStopCondition,  # noqa: E402
                  NoImprovementStopper, CompositeStopper)

import dataset as ds  # noqa: E402
import wide_dataset as wds  # noqa: E402
import metric as mt  # noqa: E402
from gepa_run import SEED_SINGLE, SYS_KEY, leaks_reference, LEAK_PENALTY  # noqa: E402
from llm_client import get_llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
AT = CFG.get("autoresearch", {})
RESULTS = ROOT / "results"
RUNS = RESULTS / "runs"
FIXED_DATA_SEED = 1234   # fixes the held-out eval set across ALL trials

# ---- search space: QUALITY knobs only (never the metric / eval set) ---------
SPACE = {
    "reflect_minibatch": [2, 3, 4, 6],
    "train_per_reviewer": [4, 8, 12, 20, 32],
    "val_size": [8, 12, 20, 30],
    "gen_max_tokens": [800, 1200, 1600, 2200],
    "gen_temperature": [0.0, 0.2, 0.4, 0.7],
    "reflect_think": [True, False],
    "sel_strategy": ["pareto", "current_best"],
    "gepa_seed": [3, 7, 11, 21],
}


def sample_config(rng):
    return {k: rng.choice(v) for k, v in SPACE.items()}


def per_knob_best(history):
    """For each knob, the value with the highest MEAN score so far (trajectory
    knowledge). Returns {knob: best_value} using only knobs with >=2 samples."""
    best = {}
    for knob, choices in SPACE.items():
        by_val = {}
        for r in history:
            v = r["config"].get(knob)
            by_val.setdefault(v, []).append(r["score"])
        ranked = [(sum(s) / len(s), v) for v, s in by_val.items() if len(s) >= 1]
        if ranked:
            best[knob] = max(ranked)[1]
    return best


def propose(history, incumbent, rng, warmup, explore_p):
    """AutoResearch-style proposal: informed hypothesis, not a random sample.

    Returns (config, rationale). Until `warmup` trials exist we spread out
    randomly; after that we hill-climb from the incumbent, nudging 1-2 knobs
    toward their historically-best values, with an occasional random explore."""
    if len(history) < warmup or incumbent is None:
        return sample_config(rng), "warmup: random sample"
    if rng.random() < explore_p:
        return sample_config(rng), "explore: random sample"
    knob_best = per_knob_best(history)
    cfg = dict(incumbent["config"])
    n_changes = 1 if rng.random() < 0.7 else 2
    knobs = rng.sample(list(SPACE), n_changes)
    notes = []
    for knob in knobs:
        target = knob_best.get(knob)
        cur = cfg.get(knob)
        if target is not None and target != cur and rng.random() < 0.7:
            cfg[knob] = target                       # move toward best-known
            notes.append(f"{knob}:{cur}->{target}")
        else:                                        # local random neighbor
            choices = [c for c in SPACE[knob] if c != cur] or SPACE[knob]
            nv = rng.choice(choices)
            cfg[knob] = nv
            notes.append(f"{knob}:{cur}->{nv}")
    return cfg, "hill-climb from t%d (%s)" % (incumbent["trial"], ", ".join(notes))


# ---- generation + adapter parameterized by the trial's gen knobs ------------
def _gen(llm, prompt, pr_input, max_tokens, temperature):
    user = ("Review this pull request now.\n\n" + pr_input +
            "\n\nWrite the review in the required format.")
    # with thinking on, do NOT cap with the small gen_max_tokens knob (it would
    # truncate the <think> block); fall back to the generous config default.
    mt = None if getattr(llm, "enable_thinking", False) else max_tokens
    from llm_client import final_review
    return final_review(llm.complete(prompt, user, max_tokens=mt, temperature=temperature))


class TunableAdapter(GEPAAdapter):
    def __init__(self, profile, workers, gen_max_tokens, gen_temperature):
        self.llm = get_llm(profile)
        self.profile = profile
        self.workers = workers
        self.gmt = gen_max_tokens
        self.gtemp = gen_temperature

    def evaluate(self, batch, candidate, capture_traces=False):
        prompt = candidate[SYS_KEY]
        leak = leaks_reference(prompt)

        def run_one(inst):
            try:
                out = _gen(self.llm, prompt, inst["input"], self.gmt, self.gtemp)
            except Exception as e:  # noqa: BLE001
                return "", 0.0, f"gen-error:{e}"
            sc, fb = mt.score_with_feedback(inst["input"], out,
                                            inst["reference_review"], self.profile)
            return out, sc, fb

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            res = list(ex.map(run_one, batch))
        outs = [r[0] for r in res]
        scores = [r[1] for r in res]
        if leak:                                  # broken-in-deployment -> penalize
            scores = [s * LEAK_PENALTY for s in scores]
        traj = None
        if capture_traces:
            note = (" LEAKAGE: refers to a 'reference review' not available at "
                    "inference; make the prompt self-contained." if leak else "")
            traj = [{"input": b["input"], "reference": b["reference_review"],
                     "generated": r[0], "score": s, "feedback": r[2] + note}
                    for b, r, s in zip(batch, res, scores)]
        return EvaluationBatch(outputs=outs, scores=scores, trajectories=traj)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        recs = []
        for tr in (eval_batch.trajectories or []):
            recs.append({
                "Inputs": tr["input"][:2500],
                "Target review to PREDICT (HIDDEN at inference)": tr["reference"][:1800],
                "Generated Outputs": tr["generated"][:1800],
                "Feedback": (f"score={tr['score']:.2f}. {tr['feedback']} Improve the "
                             "prompt so the review matches the target reviewer's "
                             "concerns and voice. CRITICAL: the prompt must be "
                             "SELF-CONTAINED — never tell the model it is given a "
                             "'reference review' or target; it is hidden at inference."),
            })
        return {c: recs for c in components_to_update}


def _reflection_lm(profile, think):
    llm = get_llm(profile)

    def _call(prompt):
        if isinstance(prompt, list):
            return llm.chat(prompt, temperature=0.7, think=think)  # no cap
        return llm.complete("", prompt, temperature=0.7, think=think)
    return _call


# ---- fixed data: eval set is identical across all trials ---------------------
def load_target(profile):
    reviewer = AT.get("tune_reviewer", "vietj")
    if AT.get("source", "wide") == "deep":
        inst = ds.build_instances()
    else:
        sel = CFG.get("selection", {})
        inst = wds.build_wide_instances(
            CFG["fib_sweep"].get("min_ref_chars", 80),
            quality_gate=sel.get("quality_gate"),
            quality_threshold=sel.get("quality_threshold", 4))
    if reviewer not in inst:
        # fall back to the most-covered reviewer available
        reviewer = max(inst, key=lambda l: len(inst[l]))
    xs = list(inst[reviewer])
    random.Random(FIXED_DATA_SEED).shuffle(xs)
    eval_n = AT.get("eval_size", 20)
    eval_fixed = xs[:eval_n]
    pool = xs[eval_n:]
    return reviewer, eval_fixed, pool


def objective(cfg, profile, eval_fixed, pool, workers, gepa_secs, patience, tag):
    train = pool[: cfg["train_per_reviewer"]]
    val = pool[cfg["train_per_reviewer"]: cfg["train_per_reviewer"] + cfg["val_size"]]
    if len(train) < 2 or len(val) < 2:
        return 0.0, "insufficient data"
    adapter = TunableAdapter(profile, workers, cfg["gen_max_tokens"],
                             cfg["gen_temperature"])
    run_dir = str(RUNS / tag)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    # comparability budget OR early-stop when the val trajectory plateaus
    stopper = CompositeStopper(TimeoutStopCondition(gepa_secs),
                               NoImprovementStopper(patience), mode="any")
    res = gepa.optimize(
        seed_candidate={SYS_KEY: SEED_SINGLE},
        trainset=train, valset=val, adapter=adapter,
        reflection_lm=_reflection_lm(profile, cfg["reflect_think"]),
        reflection_minibatch_size=cfg["reflect_minibatch"],
        candidate_selection_strategy=cfg["sel_strategy"],
        max_metric_calls=100000,
        stop_callbacks=[stopper],
        seed=cfg["gepa_seed"], run_dir=run_dir,
        display_progress_bar=False, raise_on_exception=False,
    )
    best = res.best_candidate[SYS_KEY]
    llm = get_llm(profile)

    def ev_one(inst):
        out = _gen(llm, best, inst["input"], cfg["gen_max_tokens"],
                   cfg["gen_temperature"])
        sc, _ = mt.score_with_feedback(inst["input"], out,
                                       inst["reference_review"], profile)
        return sc
    with ThreadPoolExecutor(max_workers=workers) as ex:
        scores = list(ex.map(ev_one, eval_fixed))
    return (mean(scores) if scores else 0.0), best


def run(profile="qwen"):
    workers = CFG[profile].get("max_concurrency", 4)
    gepa_secs = AT.get("gepa_seconds", 300)
    max_trials = AT.get("max_trials", 40)
    warmup = AT.get("warmup", 5)
    explore_p = AT.get("explore_p", 0.25)
    patience = AT.get("no_improve_patience", 2)
    reviewer, eval_fixed, pool = load_target(profile)
    print(f"[autoresearch] AutoResearch loop | reviewer={reviewer} "
          f"fixed_eval={len(eval_fixed)} pool={len(pool)} budget={gepa_secs}s/trial "
          f"warmup={warmup} explore_p={explore_p} patience={patience} "
          f"max_trials={max_trials}")

    jsonl = RESULTS / "autoresearch.jsonl"
    prev = []
    if jsonl.exists():
        prev = [json.loads(x) for x in jsonl.read_text().splitlines() if x.strip()]
    history = list(prev)
    start = len(prev)
    best = max(prev, key=lambda r: r["score"]) if prev else None
    rng = random.Random(7 + start)
    fout = jsonl.open("a")

    t = start
    while max_trials == 0 or t < max_trials:
        cfg, rationale = propose(history, best, rng, warmup, explore_p)
        tag = f"{profile}_autoresearch_t{t}"
        t0 = time.time()
        try:
            score, best_prompt = objective(cfg, profile, eval_fixed, pool,
                                            workers, gepa_secs, patience, tag)
        except Exception as e:  # noqa: BLE001
            score, best_prompt = 0.0, f"trial-error:{e}"
        kept = best is None or score > best["score"]
        rec = {"trial": t, "score": round(score, 4), "config": cfg,
               "rationale": rationale, "kept": kept,
               "incumbent": (best["trial"] if best else None),
               "secs": round(time.time() - t0, 1), "reviewer": reviewer,
               "eval_size": len(eval_fixed)}
        fout.write(json.dumps(rec) + "\n"); fout.flush()
        history.append(rec)
        if kept:                                     # KEEP -> new baseline
            best = rec
            (RESULTS / "autoresearch_best.json").write_text(json.dumps(
                {**rec, "best_prompt": best_prompt if isinstance(best_prompt, str)
                 else None}, indent=2))
        # else: REVERT (incumbent stays `best`); next proposal hill-climbs from it
        print(f"[autoresearch] t{t:03d} score={score:.4f} "
              f"(best={best['score']:.4f}) {'KEEP' if kept else 'revert'} | "
              f"{rationale} | {rec['secs']}s", flush=True)
        _chart(profile)
        t += 1
    fout.close()
    print(f"[autoresearch] done. best={best['score']:.4f} cfg={best['config']}")


def _chart(profile):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return
    rows = [json.loads(x) for x in (RESULTS / "autoresearch.jsonl").read_text()
            .splitlines() if x.strip()]
    if not rows:
        return
    ts = [r["trial"] for r in rows]
    sc = [r["score"] for r in rows]
    bsf, m = [], -1.0
    for s in sc:
        m = max(m, s); bsf.append(m)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(ts, sc, "o", color="#aaaaaa", ms=5, label="trial score")
    ax.plot(ts, bsf, "-", color="#1f77b4", lw=2, label="best-so-far")
    bi = max(range(len(sc)), key=lambda i: sc[i])
    ax.scatter([ts[bi]], [sc[bi]], s=160, facecolors="none", edgecolors="#d62728",
               lw=2, zorder=5, label=f"best {sc[bi]:.3f} (t{ts[bi]})")
    ax.set_xlabel("trial (AutoResearch: hill-climb + keep/revert)")
    ax.set_ylabel("held-out mimicry score (fixed eval + metric)")
    ax.set_title(f"AutoResearch — trajectory-informed keep/revert ({profile})\n"
                 f"reviewer={rows[0].get('reviewer')} · "
                 f"{rows[0].get('eval_size')} fixed eval PRs · "
                 f"{AT.get('gepa_seconds',300)}s GEPA/trial")
    ax.grid(alpha=0.3); ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / f"autoresearch_curve.{profile}.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "qwen")
