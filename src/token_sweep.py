"""1-D ablation of generation `max_tokens` on the mimicry score.

Everything else is held fixed (one prompt, the same eval PRs, temp=0). We vary
ONLY the output cap and measure (a) mimicry score and (b) the average generated
length. Expectation: score rises while the cap truncates real reviews, then goes
FLAT once the cap exceeds the natural review length (a cap is not a target — 1M
== 2200 if the model stops earlier). This locates the knee = the smallest cap
that isn't throwing away signal.

Usage: python src/token_sweep.py [profile]
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
import metric as mt  # noqa: E402
from gepa_run import SEED_SINGLE  # noqa: E402
from autoresearch import load_target, _gen  # noqa: E402
from llm_client import get_llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
RESULTS = ROOT / "results"


def fib_values(lo: int, hi: int) -> list[int]:
    a, b, out = 1, 1, []
    while a <= hi:
        if a >= lo:
            out.append(a)
        a, b = b, a + b
    return sorted(set(out))


# gen_max_tokens swept over Fibonacci caps: dense through the truncation knee,
# sparse over the saturated tail.
VALUES = fib_values(3, 2584)   # 3,5,8,13,21,34,55,89,144,233,377,610,987,1597,2584
LABEL = "fib"


def fixed_prompt():
    p = RESULTS / "autoresearch_best.json"
    if p.exists():
        bp = json.loads(p.read_text()).get("best_prompt")
        if bp:
            return bp, "autoresearch_best"
    return SEED_SINGLE, "seed_single"


def run(profile="qwen"):
    workers = CFG[profile].get("max_concurrency", 4)
    reviewer, eval_fixed, _ = load_target(profile)
    prompt, psrc = fixed_prompt()
    llm = get_llm(profile)
    # reference length context (tokens ~= chars/4)
    ref_chars = mean(len(i["reference_review"]) for i in eval_fixed)
    print(f"[tok] reviewer={reviewer} eval={len(eval_fixed)} prompt={psrc} "
          f"avg_ref~{ref_chars/4:.0f} tok ({ref_chars:.0f} chars)")

    rows = []
    for mtok in VALUES:
        def one(inst):
            out = _gen(llm, prompt, inst["input"], mtok, 0.0)
            sc, _ = mt.score_with_feedback(inst["input"], out,
                                           inst["reference_review"], profile)
            return sc, len(out)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(one, eval_fixed))
        score = mean(r[0] for r in res)
        out_chars = mean(r[1] for r in res)
        rows.append({"max_tokens": mtok, "score": round(score, 4),
                     "avg_out_tok": round(out_chars / 4), "avg_out_chars": round(out_chars)})
        print(f"[tok] max_tokens={mtok:5d}  score={score:.4f}  "
              f"avg_out~{out_chars/4:.0f} tok", flush=True)
        out = {"reviewer": reviewer, "prompt_source": psrc,
               "avg_ref_tok": round(ref_chars / 4), "points": rows}
        (RESULTS / f"token_sweep_{LABEL}.{profile}.json").write_text(
            json.dumps(out, indent=2))
    _chart(out, profile)
    print(f"[tok] wrote results/token_sweep_{LABEL}.{profile}.json/.png")


def _chart(out, profile):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pts = out["points"]
    x = [p["max_tokens"] for p in pts]
    sc = [p["score"] for p in pts]
    ol = [p["avg_out_tok"] for p in pts]
    fig, ax1 = plt.subplots(figsize=(8.5, 5))
    ax1.plot(x, sc, "-o", color="#1f77b4", lw=2, label="mimicry score")
    ax1.set_xscale("log")
    ax1.set_xlabel("gen_max_tokens — Fibonacci caps (log scale)")
    ax1.set_ylabel("mimicry score", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.grid(alpha=0.3, which="both")
    ax2 = ax1.twinx()
    ax2.plot(x, ol, "--s", color="#2ca02c", label="avg output length (tok)")
    ax2.axhline(out["avg_ref_tok"], ls=":", color="#d62728",
                label=f"avg reference len ({out['avg_ref_tok']} tok)")
    ax2.set_ylabel("avg output length (tokens)", color="#2ca02c")
    ax2.tick_params(axis="y", labelcolor="#2ca02c")
    best = max(pts, key=lambda p: p["score"])
    ax1.set_title(f"Output-cap ablation ({profile}) — reviewer {out['reviewer']}\n"
                  f"score saturates once cap > natural review length · "
                  f"best @ {best['max_tokens']} tok")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [l.get_label() for l in lines], loc="center right", fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / f"token_sweep_{LABEL}.{profile}.png", dpi=130)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "qwen")
