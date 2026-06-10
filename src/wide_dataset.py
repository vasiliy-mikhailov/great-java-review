"""Build review-mimicry instances for the WIDE reviewer pool, directly from the
discovery index (data/cache/comments_index.jsonl) with ZERO extra API calls.

Each inline review comment already carries its `diff_hunk`, file path and body,
so a "review unit" (comments grouped by pull_request_review_id) is enough to make
a GEPA instance:

  input            : the diff hunks the reviewer commented on (the code under review)
  reference_review : the reviewer's actual inline comments, anchored to file:line

This is what lets the Fibonacci sweep scale to ~10k reviewers cheaply: the wide
pool is mined entirely from data we already crawled.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import crawl  # noqa: E402  (reuses _review_units / is_bot / index path)

ROOT = Path(__file__).resolve().parent.parent


def _render_reference(comments: list) -> str:
    pts = []
    for c in comments:
        path = c.get("path") or "?"
        line = c.get("line")
        loc = f"{path}:{line}" if line else path
        b = (c.get("body") or "").strip()
        if b:
            pts.append(f"- [{loc}] {b}")
    return ("POINTS:\n" + "\n".join(pts)) if pts else ""


def _render_input(repo, pr, comments, max_chars: int = 6000) -> str:
    seen = set()
    blocks = []
    for c in comments:
        hunk = (c.get("diff_hunk") or "").strip()
        if not hunk:
            continue
        path = c.get("path") or "?"
        key = (path, hunk)
        if key in seen:
            continue
        seen.add(key)
        blocks.append(f"\n// File: {path}\n{hunk}")
    if not blocks:
        return ""
    head = (f"REPO: {repo}\nPR #{pr}\n"
            "Code under review (the diff hunks this reviewer commented on):\n")
    return (head + "".join(blocks))[:max_chars]


import json  # noqa: E402

QUALITY_CACHE = ROOT / "data" / "cache" / "quality.jsonl"


def quality_key(repo, pr, rid) -> str:
    return f"{repo}#{pr}#{rid}"


def load_quality_cache() -> dict:
    d = {}
    if QUALITY_CACHE.exists():
        for line in QUALITY_CACHE.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line); d[r["key"]] = r["score"]
                except Exception:  # noqa: BLE001
                    pass
    return d


def build_wide_instances(min_ref_chars: int = 80, substantive_only: bool = True,
                         quality_gate: str | None = None, quality_threshold: int = 4):
    """Return {login: [instance, ...]} mined from the discovery comment index.

    Contract (P3): only HIGH-QUALITY reviews are kept (mimic substantive feedback,
    not every comment). Two-stage gate:
      (1) heuristic floor — crawl.is_substantive_unit AND reference >= min_ref_chars.
      (2) if quality_gate == 'qwen': keep only units whose CACHED Qwen rubric score
          (data/cache/quality.jsonl, populated by quality_judge.py) is >=
          quality_threshold. Uncached units are dropped (judge them first)."""
    units = crawl._review_units()          # {(repo,pr,rid,login): {comments:[...]}}
    qcache = load_quality_cache() if quality_gate == "qwen" else None
    out: dict[str, list] = {}
    for (repo, pr, rid, login), u in units.items():
        if crawl.is_bot(login):
            continue
        comments = u["comments"]
        if substantive_only and not crawl.is_substantive_unit(comments):
            continue
        ref = _render_reference(comments)
        if len(ref) < min_ref_chars:
            continue
        if qcache is not None and qcache.get(quality_key(repo, pr, rid), 0) < quality_threshold:
            continue
        inp = _render_input(repo, pr, comments)
        if not inp:
            continue
        out.setdefault(login, []).append({
            "reviewer": login,
            "repo": repo,
            "pr": pr,
            "review_id": rid,
            "input": inp,
            "reference_review": ref,
            "n_points": len(comments),
        })
    return out


if __name__ == "__main__":
    inst = build_wide_instances()
    n_inst = sum(len(v) for v in inst.values())
    print(f"wide pool: {len(inst)} reviewers, {n_inst} instances")
    for login, xs in sorted(inst.items(), key=lambda kv: -len(kv[1]))[:15]:
        avg = sum(len(i["reference_review"]) for i in xs) / len(xs)
        print(f"  {login:24s} {len(xs):4d} instances, avg ref {avg:.0f} chars")
