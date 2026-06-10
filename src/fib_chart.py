"""Plot the Fibonacci scaling curve: universal-prompt mimicry score vs. the
number of reviewers k it was optimized on (log-x).
Reads results/fib_sweep.<profile>.<eval_mode>.json.

Usage: python src/fib_chart.py [profile] [eval_mode]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _find(profile, mode):
    if mode:
        return ROOT / "results" / f"fib_sweep.{profile}.{mode}.json"
    for cand in [f"fib_sweep.{profile}.in_domain.json",
                 f"fib_sweep.{profile}.population.json",
                 f"fib_sweep.{profile}.json"]:
        p = ROOT / "results" / cand
        if p.exists():
            return p
    return ROOT / "results" / f"fib_sweep.{profile}.json"


def chart(profile: str = "qwen", mode: str | None = None):
    path = _find(profile, mode)
    d = json.loads(path.read_text())
    mode = d.get("eval_mode", "population")
    pts = sorted(d["points"], key=lambda p: p["k"])
    ks = [p["k"] for p in pts]
    ev = [p["eval_score"] for p in pts]
    base = ev[0]                      # k=1 as the practical reference
    best = max(pts, key=lambda p: p["eval_score"])
    ylab = ("in-domain mimicry score\n(held-out PRs of the k trained reviewers)"
            if mode == "in_domain" else "held-out review-mimicry score (population)")
    pool = d.get("n_usable_reviewers", d.get("n_reviewers", "?"))

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(ks, ev, "-o", color="#1f77b4", lw=2, ms=6,
            label="universal prompt")
    ax.axhline(base, ls="--", color="gray", lw=1,
               label=f"k=1 reference ({base:.3f})")
    ax.scatter([best["k"]], [best["eval_score"]], s=160, facecolors="none",
               edgecolors="#d62728", lw=2, zorder=5,
               label=f"best: k={best['k']} ({best['eval_score']:.3f})")
    ax.set_xscale("log")
    ax.set_xlabel("number of reviewers k the one prompt must mimic (log scale)")
    ax.set_ylabel(ylab)
    ax.set_title(f"Fibonacci scaling — one universal Java-review prompt "
                 f"({profile}, {mode})\nsource={d['source']} · "
                 f"usable pool={pool} reviewers")
    ax.grid(alpha=0.3, which="both")
    ax.legend(loc="best", fontsize=8)
    # annotate every Fibonacci point with its k
    for p in pts:
        ax.annotate(str(p["k"]), (p["k"], p["eval_score"]),
                    textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=7, color="#555")
    fig.tight_layout()
    out = ROOT / "results" / f"fib_scaling_curve.{profile}.{mode}.png"
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")
    print(f"  best k={best['k']} eval={best['eval_score']:.4f}; "
          f"k=1 {base:.4f}; span {min(ev):.4f}..{max(ev):.4f}")
    return out


if __name__ == "__main__":
    chart(sys.argv[1] if len(sys.argv) > 1 else "qwen",
          sys.argv[2] if len(sys.argv) > 2 else None)
