"""Turn excellent_reviews.json into GEPA instances.

Each instance is one (PR -> reviewer's review) example:
  input            : the PR context the reviewer saw (title/body/files/diff)
  reference_review : the reviewer's real review rendered in a canonical format
                     (summary + file-anchored points) that the model must mimic
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "excellent_reviews.json"


def render_reference(review: dict) -> str:
    """Canonical rendering of a real review: summary + anchored points."""
    parts = []
    body = (review.get("review_body") or "").strip()
    if body:
        parts.append("SUMMARY:\n" + body)
    pts = []
    for c in review.get("inline_comments", []):
        path = c.get("path") or "?"
        line = c.get("line")
        loc = f"{path}:{line}" if line else path
        b = (c.get("body") or "").strip()
        if b:
            pts.append(f"- [{loc}] {b}")
    if pts:
        parts.append("POINTS:\n" + "\n".join(pts))
    return "\n\n".join(parts).strip()


def render_pr_input(review: dict, max_chars: int = 7000) -> str:
    files = ", ".join(review.get("pr_files", [])[:25])
    stats = review.get("pr_stats", {})
    s = (
        f"REPO: {review.get('repo')}\n"
        f"PR #{review.get('pr')}: {review.get('pr_title','')}\n"
        f"Changed files ({stats.get('changed_files')}): {files}\n"
        f"Diff (+{stats.get('additions')}/-{stats.get('deletions')}):\n"
        f"PR DESCRIPTION:\n{(review.get('pr_body') or '')[:1500]}\n\n"
        f"DIFF:\n{review.get('pr_diff','')}"
    )
    return s[:max_chars]


def build_instances(min_ref_chars: int = 60, quality_gate: str | None = None,
                    quality_threshold: int = 4):
    """Full-MR instances from excellent_reviews.json (input = the WHOLE PR).

    If quality_gate == 'qwen', keep only reviews whose CACHED Qwen rubric score
    (data/cache/quality.jsonl, full-MR judged) is >= quality_threshold."""
    import wide_dataset as wds  # reuse the shared quality cache + key
    data = json.loads(OUT_PATH.read_text())
    reviewers = data["reviewers"]
    qcache = wds.load_quality_cache() if quality_gate == "qwen" else None
    out = {}
    for login, blob in reviewers.items():
        insts = []
        for rv in blob.get("reviews", []):
            ref = render_reference(rv)
            if len(ref) < min_ref_chars:
                continue
            if qcache is not None and qcache.get(
                    wds.quality_key(rv.get("repo"), rv.get("pr"),
                                    rv.get("review_id")), 0) < quality_threshold:
                continue
            insts.append({
                "reviewer": login,
                "repo": rv.get("repo"),
                "pr": rv.get("pr"),
                "review_id": rv.get("review_id"),
                "pr_url": rv.get("pr_url"),
                "input": render_pr_input(rv),
                "reference_review": ref,
                "n_points": len(rv.get("inline_comments", [])),
            })
        if insts:
            out[login] = insts
    return out


def split(insts: list, train_n: int, val_n: int, seed: int = 7):
    r = random.Random(seed)
    idx = list(range(len(insts)))
    r.shuffle(idx)
    tr = [insts[i] for i in idx[:train_n]]
    va = [insts[i] for i in idx[train_n:train_n + val_n]]
    return tr, va


def split3(insts: list, train_n: int, val_n: int, test_n: int, seed: int = 7):
    """Disjoint train/val/test split (held-out test for fair comparison)."""
    r = random.Random(seed)
    idx = list(range(len(insts)))
    r.shuffle(idx)
    a = train_n
    b = train_n + val_n
    c = train_n + val_n + test_n
    return ([insts[i] for i in idx[:a]],
            [insts[i] for i in idx[a:b]],
            [insts[i] for i in idx[b:c]])


if __name__ == "__main__":
    inst = build_instances()
    print(f"{len(inst)} reviewers with usable instances")
    for login, xs in sorted(inst.items(), key=lambda kv: -len(kv[1]))[:15]:
        avg = sum(len(i["reference_review"]) for i in xs) / len(xs)
        print(f"  {login:24s} {len(xs):4d} instances, avg ref {avg:.0f} chars")
