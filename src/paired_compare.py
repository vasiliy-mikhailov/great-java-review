"""Paired comparison: 'MR only' (diff-only) vs 'MR + code' (OpenHands reads repo).

Powered for a MEDIUM effect: n=34 distinct gold PRs, k=3 rollouts per condition
per PR (averaged to tame the OpenHands synthesis-stall variance), paired
Wilcoxon signed-rank over the per-PR deltas.

  MR only   = diff_only_review(pr_input)        # Qwen, diff in context, NO tools
  MR + code = oh_review_delegate(repo_dir, ...)  # OpenHands, reads repo @ base

PRs drawn from the dual-judged gold pool (clean_both_technical.json) AND restricted
to already-cloned repos, so no live cloning and the 1-worker git limit is a non-issue.
Scores are vs the human reviewer (metric.score_with_feedback). Saves incrementally.

  ./venv-oh/bin/python src/paired_compare.py --n 34 --k 3
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import warnings
from pathlib import Path
from statistics import mean, pstdev

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from wide_dataset import quality_key  # noqa: E402
from agent_review import diff_only_review  # noqa: E402
from oh_delegate import oh_review_delegate  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402

GOLD_POOL = "data/cache/clean_both_technical.json"
OUT = Path("results/paired_compare.json")


def select_prs(n, max_per_repo=6):
    """Distinct gold PRs whose repo is already cloned, round-robin across repos
    for diversity (<=max_per_repo each)."""
    gold = set(json.load(open(GOLD_POOL)))
    cloned = {p.name.replace("__", "/") for p in Path("data/repos").iterdir()
              if p.is_dir()}
    inst = ds.build_instances()
    # bucket candidate (one review per PR) by repo
    buckets, seen = {}, set()
    for rows in inst.values():
        for x in rows:
            key = (x["repo"], x["pr"])
            if key in seen or x["repo"] not in cloned:
                continue
            if quality_key(x["repo"], x["pr"], x["review_id"]) not in gold:
                continue
            seen.add(key)
            buckets.setdefault(x["repo"], []).append(x)
    # round-robin draw for diversity
    order = sorted(buckets, key=lambda r: -len(buckets[r]))
    picked, taken = [], {r: 0 for r in order}
    while len(picked) < n and any(taken[r] < min(max_per_repo, len(buckets[r]))
                                  for r in order):
        for r in order:
            if taken[r] < min(max_per_repo, len(buckets[r])):
                picked.append(buckets[r][taken[r]]); taken[r] += 1
                if len(picked) >= n:
                    break
    return picked


def wilcoxon_signed_rank(deltas):
    """Two-sided Wilcoxon signed-rank with normal approx + continuity correction.
    Zeros dropped (Wilcoxon convention). Returns (W, z, p, n_nonzero)."""
    d = [x for x in deltas if abs(x) > 1e-9]
    n = len(d)
    if n == 0:
        return 0.0, 0.0, 1.0, 0
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        avg = (i + 1 + j + 1) / 2.0          # average rank for ties
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(ranks[i] for i in range(n) if d[i] > 0)
    w_minus = sum(ranks[i] for i in range(n) if d[i] < 0)
    W = min(w_plus, w_minus)
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return W, 0.0, 1.0, n
    z = (W - mu + 0.5) / sigma               # continuity-corrected
    p = 2 * 0.5 * math.erfc(abs(z) / math.sqrt(2))
    return W, z, min(p, 1.0), n


def summarize(rows):
    deltas = [r["delta"] for r in rows]
    md, sd = mean(deltas), (pstdev(deltas) if len(deltas) > 1 else 0.0)
    # sample SD for d_z
    if len(deltas) > 1:
        ssd = math.sqrt(sum((x - md) ** 2 for x in deltas) / (len(deltas) - 1))
    else:
        ssd = 0.0
    dz = md / ssd if ssd else 0.0
    W, z, p, nnz = wilcoxon_signed_rank(deltas)
    wins = sum(d > 0 for d in deltas)
    return {
        "n_pairs": len(rows),
        "mr_only_mean": round(mean(r["mr_only_mean"] for r in rows), 4),
        "mr_code_mean": round(mean(r["mr_code_mean"] for r in rows), 4),
        "mean_delta": round(md, 4),
        "sd_delta": round(ssd, 4),
        "cohen_dz": round(dz, 3),
        "mr_code_wins": f"{wins}/{len(rows)}",
        "wilcoxon_W": round(W, 1),
        "wilcoxon_z": round(z, 3),
        "p_value": round(p, 4),
        "significant_0.05": p < 0.05,
    }


MIN_REVIEW_CHARS = 60   # below this = empty/failed (endpoint 500 / dropped socket /
#                         stall), so RETRY instead of recording a junk 0.0.


def _endpoint_healthy(profile="qwen", timeout=10):
    """Cheap liveness probe (GET /models). The shared GPU 500s under load; checking
    it costs ~0.3s and saves a doomed ~13-min rollout."""
    import urllib.request as _u
    from oh_review import CFG
    c = CFG[profile]
    key = os.environ.get(c.get("api_key_env", "QWEN_API_KEY"), "x")
    try:
        req = _u.Request(c["base_url"].rstrip("/") + "/models",
                         headers={"Authorization": f"Bearer {key}"})
        with _u.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _wait_for_endpoint(profile="qwen", interval=30, max_wait=3600):
    """Block (in-run) until the endpoint answers, so we ride out a flaky/down spell
    BEFORE launching an expensive rollout instead of burning it and recording 0.0.
    Bounded by max_wait so a truly-dead endpoint can't hang the run forever."""
    import time as _t
    waited = 0
    while not _endpoint_healthy(profile):
        print(f"    [endpoint] unhealthy — waiting {interval}s (total {waited}s)…",
              flush=True)
        _t.sleep(interval)
        waited += interval
        if waited >= max_wait:
            print(f"    [endpoint] still down after {max_wait}s — proceeding anyway",
                  flush=True)
            return False
    if waited:
        print(f"    [endpoint] recovered after {waited}s", flush=True)
    return True


def _scored_review(label, fn, args, pr_input, human, profile, attempts=3):
    """Run a review call; if it returns empty/short OR raises (transient endpoint
    500s, dropped sockets), RETRY rather than scoring a junk 0.0 — those are
    infrastructure noise, not 'the agent failed to review', and they unfairly
    pollute the comparison. Returns (score, review). Records ~0 only if EVERY
    attempt failed (a real persistent failure)."""
    rv = ""
    for a in range(attempts):
        _wait_for_endpoint(profile)   # deal with a flaky/down endpoint IN-RUN, BEFORE
        #                               spending an expensive rollout on it (pre-flight
        #                               on attempt 0, recovery-wait before each retry)
        try:
            out = fn(*args)
            rv = out[0] if isinstance(out, tuple) else out
        except Exception as e:  # noqa: BLE001
            print(f"    {label} attempt {a + 1}/{attempts} EXC: {e}", flush=True)
            rv = ""
        if rv and len(rv.strip()) >= MIN_REVIEW_CHARS:
            s, _ = mt.score_with_feedback(pr_input, rv, human, profile)
            if a:
                print(f"    {label} recovered on attempt {a + 1}", flush=True)
            return round(s, 4), rv
        print(f"    {label} attempt {a + 1}/{attempts} empty/short "
              f"(len={len(rv.strip()) if rv else 0}) — retry", flush=True)
    print(f"    {label} ALL {attempts} attempts failed → recording 0.0", flush=True)
    return 0.0, rv


def run(n=34, k=3, profile="qwen"):
    prs = select_prs(n)
    print(f"selected {len(prs)} PRs across "
          f"{len({x['repo'] for x in prs})} repos", flush=True)
    # RESUME (pure bookkeeping, not a cap): keep PR rows already on disk so the
    # slow unbounded grind accumulates across socket-deaths / lid-closes / restarts.
    rows, done = [], set()
    if OUT.exists():
        try:
            rows = json.load(open(OUT)).get("rows", [])
            done = {(r["repo"], r["pr"]) for r in rows}
            print(f"resume: {len(done)} PRs already done, skipping them", flush=True)
        except Exception:  # noqa: BLE001
            rows, done = [], set()
    for idx, x in enumerate(prs, 1):
        repo, pr = x["repo"], x["pr"]
        if (repo, pr) in done:
            continue
        sha = base_sha(repo, pr)
        if not sha:
            print(f"[{idx}/{len(prs)}] {repo}#{pr} no base sha, skip", flush=True)
            continue
        d = ensure_repo(repo, sha)
        if d is None:
            print(f"[{idx}/{len(prs)}] {repo}#{pr} checkout failed, skip", flush=True)
            continue
        pr_input, human = x["input"], x["reference_review"]
        mr_only, mr_code = [], []
        for j in range(k):
            s, _ = _scored_review("mr_only", diff_only_review,
                                  (pr_input, profile), pr_input, human, profile)
            mr_only.append(s)
            s, _ = _scored_review("mr_code", oh_review_delegate,
                                  (str(d), pr_input, profile), pr_input, human, profile)
            mr_code.append(s)
        mo, mc = mean(mr_only), mean(mr_code)
        row = {"repo": repo, "pr": pr, "reviewer": x.get("reviewer"),
               "mr_only_scores": mr_only, "mr_code_scores": mr_code,
               "mr_only_mean": round(mo, 4), "mr_code_mean": round(mc, 4),
               "delta": round(mc - mo, 4)}
        rows.append(row)
        print(f"[{idx}/{len(prs)}] {repo.split('/')[-1]}#{pr}  "
              f"mr_only {mo:.3f}  mr_code {mc:.3f}  Δ {mc-mo:+.3f}", flush=True)
        OUT.write_text(json.dumps({"rows": rows}, indent=2))
    if rows:
        summary = summarize(rows)
        OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
        print("\n=== SUMMARY ===")
        for kk, vv in summary.items():
            print(f"  {kk}: {vv}")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=34)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--profile", default="qwen")
    a = ap.parse_args()
    run(a.n, a.k, a.profile)
