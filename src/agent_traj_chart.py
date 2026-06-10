"""Trajectory chart for the Attempt-2 agent (P11).

Two panels:
  (top)    one row per rollout = the agent's tool-call TIMELINE, colour-coded by
           tool (repomap/ls/read_file/grep), REPEATED identical calls hatched
           (wasted budget), a flag if it self-terminated; annotated with Δ.
  (bottom) Δ (agent+repo - diff-only) vs #tool calls, coloured by diff-only base
           score — shows the failure mode: long trajectories hurt HIGH-base PRs.

Source = results/agent_poc_batch.json (each row has tools[], delta, diff_only).
The same renderer is reused on GEPA-agent runs (pass --src <rows.json>).

Usage: python src/agent_traj_chart.py [--src results/agent_poc_batch.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))

COLORS = {"repomap": "#7b3fe4", "ls": "#2b9348", "read_file": "#1f77b4",
          "grep": "#e07a00", "review": "#444444", "no-action": "#cc0000"}


def _seq(tools):
    return [t.split()[0] if t else "?" for t in tools]


def render(rows, out):
    rows = [r for r in rows if r.get("tools")]
    if not rows:
        print("no rows with trajectories"); return
    n = len(rows)
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(12, 1.0 * n + 4.2),
        gridspec_kw={"height_ratios": [max(2, n), 4]})

    # ---- top: per-rollout tool timeline -------------------------------------
    for i, r in enumerate(rows):
        seq = _seq(r["tools"])
        seen = Counter()
        for j, (raw, tool) in enumerate(zip(r["tools"], seq)):
            seen[raw] += 1
            repeat = seen[raw] > 1 and tool in ("grep", "read_file", "ls")
            ax.barh(i, 1, left=j, height=0.72,
                    color=COLORS.get(tool, "#999"),
                    hatch="////" if repeat else None,
                    edgecolor="white", linewidth=0.4)
        term = seq[-1] in ("review", "no-action")
        d = r.get("delta", 0.0)
        ax.text(len(seq) + 0.3, i,
                f"Δ{d:+.3f}  {len(seq)}t  {'■stop' if term else '▶budget!'}",
                va="center", fontsize=8,
                color=("#2b9348" if d > 0 else "#cc0000"))
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{r.get('reviewer','?')}\n{r.get('repo','').split('/')[-1]}#{r.get('pr','')}"
                        for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("tool-call step  (hatched = REPEAT of an earlier identical call = wasted budget)")
    ax.set_title("Agent investigation trajectories (Attempt 2 / P11)", fontweight="bold")
    ax.legend(handles=[Patch(facecolor=c, label=k) for k, c in COLORS.items()],
              ncol=6, fontsize=8, loc="upper right")
    ax.set_xlim(0, max(len(_seq(r["tools"])) for r in rows) + 6)

    # ---- bottom: Δ vs budget, coloured by base score ------------------------
    xs = [len([t for t in r["tools"] if not t.startswith(("review", "no-action"))])
          for r in rows]
    ys = [r.get("delta", 0.0) for r in rows]
    cs = [r.get("diff_only", 0.0) for r in rows]
    sc = ax2.scatter(xs, ys, c=cs, cmap="coolwarm", s=120, edgecolor="k", zorder=3)
    for x, y, r in zip(xs, ys, rows):
        ax2.annotate(r.get("reviewer", ""), (x, y), fontsize=7,
                     xytext=(4, 4), textcoords="offset points")
    ax2.axhline(0, color="#888", lw=1, ls="--")
    ax2.set_xlabel("# tool calls (investigation length)")
    ax2.set_ylabel("Δ  (agent+repo − diff-only)")
    ax2.set_title("Δ vs investigation length — warm = high diff-only base "
                  "(where over-exploration hurts)", fontsize=10)
    fig.colorbar(sc, ax=ax2, label="diff-only base score")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="results/agent_poc_batch.json")
    ap.add_argument("--out", default="results/agent_trajectories.png")
    a = ap.parse_args()
    data = json.load(open(a.src))
    render(data.get("rows", data), a.out)
