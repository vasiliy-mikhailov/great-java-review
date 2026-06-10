"""Plot a GEPA convergence chart from a run_dir produced by gepa.optimize.

Two panels:
  (top)    full-validation score per proposed candidate + best-so-far (step) +
           the seed/base score reference line.
  (bottom) reflection dynamics: the current best vs. the GEPA-proposed candidate
           on the reflection minibatch -> shows when proposals overfit the tiny
           minibatch and fail to generalize to the full val set.

Usage: python src/gepa_chart.py <run_dir> [out.png] [title]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def parse_txt(run_dir: Path):
    txt = (run_dir / "run_log.txt").read_text()
    base = None
    m = re.search(r"Base program full valset score:\s*([0-9.]+)", txt)
    if m:
        base = float(m.group(1))
    cand = [float(x) for x in re.findall(
        r"Valset score for new program:\s*([0-9.]+)", txt)]
    best = [float(x) for x in re.findall(
        r"Best valset aggregate score so far:\s*([0-9.]+)", txt)]
    return base, cand, best


def parse_json(run_dir: Path):
    p = run_dir / "run_log.json"
    if not p.exists():
        return [], []
    data = json.loads(p.read_text())
    old_mb = [mean(e["subsample_scores"]) for e in data if e.get("subsample_scores")]
    new_mb = [mean(e["new_subsample_scores"]) for e in data
              if e.get("new_subsample_scores")]
    return old_mb, new_mb


def chart(run_dir: str, out: str | None = None, title: str | None = None):
    rd = Path(run_dir)
    base, cand, best = parse_txt(rd)
    old_mb, new_mb = parse_json(rd)
    tag = rd.name
    out = out or f"results/gepa_convergence_{tag}.png"
    title = title or f"GEPA convergence — {tag}"

    # best-so-far series including the base at iteration 0
    bsf = ([base] if base is not None else []) + best
    bx = list(range(len(bsf)))
    cx = list(range(1, len(cand) + 1))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)

    if base is not None:
        ax1.axhline(base, ls="--", color="gray", lw=1,
                    label=f"seed prompt ({base:.3f})")
    ax1.plot(bx, bsf, "-o", color="#1f77b4", lw=2, label="best-so-far (val)")
    if cand:
        ax1.plot(cx, cand, "s", color="#d62728", ms=7, alpha=0.8,
                 label="proposed candidate (val)")
    ax1.set_ylabel("full-val mimicry score")
    ax1.set_title(title)
    ax1.legend(loc="best", fontsize=8)
    ax1.grid(alpha=0.3)

    if old_mb and new_mb:
        mx = list(range(1, len(new_mb) + 1))
        ax2.plot(mx, old_mb[:len(mx)], "-o", color="#7f7f7f",
                 label="current best on minibatch")
        ax2.plot(mx, new_mb, "-^", color="#2ca02c",
                 label="GEPA proposal on minibatch")
        ax2.fill_between(mx, old_mb[:len(mx)], new_mb, color="#2ca02c",
                         alpha=0.12)
        ax2.set_ylabel("reflection minibatch score")
        ax2.legend(loc="best", fontsize=8)
        ax2.grid(alpha=0.3)
    ax2.set_xlabel("GEPA iteration (reflective proposal step)")

    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")
    print(f"  seed/base val = {base}")
    print(f"  best-so-far   = {bsf}")
    print(f"  candidate val = {cand}")
    return out


if __name__ == "__main__":
    rd = sys.argv[1] if len(sys.argv) > 1 else "results/runs/qwen_fibwide_k1"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    title = sys.argv[3] if len(sys.argv) > 3 else None
    chart(rd, out, title)
