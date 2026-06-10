"""Attempt 2 PoC — confirmation batch.

Runs the diff-only vs agent+repo comparison on one code-dependent review per
small/clonable repo (diverse reviewers), to check the +Δ from repo access is
consistent (not the smallrye#1270 fluke). Writes results/agent_poc_batch.json.

Usage: python src/agent_poc_batch.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_review import diff_only_review, agent_review  # noqa: E402

GH = "/opt/homebrew/bin/gh"
# small→medium, fast to clone; diverse reviewers
REPOS = ["smallrye/smallrye-config", "agroal/agroal",
         "sevntu-checkstyle/sevntu.checkstyle", "quarkiverse/quarkus-mcp-server",
         "SaptarshiSarkar12/Drifty", "qubole/rubix", "square/okhttp",
         "eclipse-vertx/vert.x"]
N_TARGET = 5


def base_sha(repo, pr):
    r = subprocess.run([GH, "api", f"/repos/{repo}/pulls/{pr}", "--jq", ".base.sha"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def ensure_repo(repo, sha):
    d = Path("data/repos") / repo.replace("/", "__")
    if not d.exists():
        print(f"  cloning {repo} ...", flush=True)
        if subprocess.run(["git", "clone", "--quiet", f"https://github.com/{repo}",
                           str(d)]).returncode != 0:
            return None
    if subprocess.run(["git", "-C", str(d), "checkout", "--quiet", sha],
                      capture_output=True).returncode != 0:
        subprocess.run(["git", "-C", str(d), "fetch", "--quiet", "origin", sha],
                       capture_output=True)
        if subprocess.run(["git", "-C", str(d), "checkout", "--quiet", sha],
                          capture_output=True).returncode != 0:
            return None
    return d


def pick():
    raw = json.load(open("excellent_reviews.json"))["reviewers"]
    inst = ds.build_instances()
    imap = {(x["repo"], str(x["pr"])): x for v in inst.values() for x in v}
    chosen = []
    for repo in REPOS:
        if len(chosen) >= N_TARGET:
            break
        for login, b in raw.items():
            hit = False
            for rv in b["reviews"]:
                if rv["repo"] != repo:
                    continue
                n = len(rv.get("inline_comments", []))
                ref = " ".join(c.get("body", "") for c in rv["inline_comments"])
                if 2 <= n <= 6 and 80 < len(ref) < 1000 and (repo, str(rv["pr"])) in imap:
                    chosen.append((repo, rv["pr"], login)); hit = True; break
            if hit:
                break
    return chosen, imap


def run():
    chosen, imap = pick()
    print("targets:", [(r, p, l) for r, p, l in chosen], flush=True)
    rows = []
    for repo, pr, login in chosen:
        x = imap[(repo, str(pr))]
        sha = base_sha(repo, pr)
        print(f"\n=== {repo}#{pr} ({login})  base={sha[:10]} ===", flush=True)
        d = ensure_repo(repo, sha)
        if d is None:
            print("  clone/checkout failed, skip"); continue
        do = diff_only_review(x["input"])
        ds_s, _ = mt.score_with_feedback(x["input"], do, x["reference_review"])
        ar, trace = agent_review(d, x["input"])   # MAX_STEPS=200 safety ceiling, not a target
        ar_s, _ = mt.score_with_feedback(x["input"], ar, x["reference_review"])
        rows.append({"repo": repo, "pr": pr, "reviewer": login,
                     "diff_only": round(ds_s, 4), "agent_repo": round(ar_s, 4),
                     "delta": round(ar_s - ds_s, 4), "tool_calls": len(trace),
                     "tools": [t for t, _ in trace]})
        print(f"  diff-only {ds_s:.3f}  agent+repo {ar_s:.3f}  Δ {ar_s-ds_s:+.3f}  "
              f"({len(trace)} tools)", flush=True)
        Path("results/agent_poc_batch.json").write_text(json.dumps(
            {"rows": rows}, indent=2))
    if rows:
        agg = {"diff_only": round(mean(r["diff_only"] for r in rows), 4),
               "agent_repo": round(mean(r["agent_repo"] for r in rows), 4),
               "mean_delta": round(mean(r["delta"] for r in rows), 4),
               "n": len(rows), "agent_wins": sum(r["delta"] > 0 for r in rows)}
        Path("results/agent_poc_batch.json").write_text(json.dumps(
            {"aggregate": agg, "rows": rows}, indent=2))
        print(f"\n=== AGGREGATE ({agg['n']}): diff-only {agg['diff_only']} -> "
              f"agent+repo {agg['agent_repo']}  (mean Δ {agg['mean_delta']:+.3f}, "
              f"agent wins {agg['agent_wins']}/{agg['n']}) ===")


if __name__ == "__main__":
    run()
