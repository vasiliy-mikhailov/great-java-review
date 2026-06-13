"""v8 repo access (P12) — base_sha from a host-built cache, offline checkout.

The hermetic container has no `gh` CLI/token, so PR base SHAs are pre-resolved
ON THE HOST into results/base_sha_cache.json (key "repo#pr") and read here. The
repos and their pull/N/head branches are already fetched locally (mounted), so
ensure_repo's checkout works offline; full_diff likewise reuses the local
pr-<pr>-head branch.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # current_attempt
CACHE = ROOT / "results" / "base_sha_cache.json"
GH = os.environ.get("GH_BIN", "gh")


def _cache():
    try:
        return json.load(open(CACHE))
    except Exception:  # noqa: BLE001
        return {}


def base_sha(repo, pr):
    """PR base commit SHA. Cache first (container path); fall back to gh on the host
    and warm the cache. Raises if neither works (never silently return '')."""
    key = f"{repo}#{pr}"
    c = _cache()
    if c.get(key):
        return c[key]
    r = subprocess.run([GH, "api", f"/repos/{repo}/pulls/{pr}", "--jq", ".base.sha"],
                       capture_output=True, text=True)
    sha = r.stdout.strip()
    if not sha:
        raise RuntimeError(f"base_sha miss for {key}: not in {CACHE} and gh failed "
                           f"({r.stderr.strip()[:120]}). Run the host prep to warm the cache.")
    c[key] = sha
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(c, open(CACHE, "w"), indent=1)
    return sha


def ensure_repo(repo, sha):
    """Check the repo out at `sha`. Offline if the SHA is already local (it is, from
    prior runs); falls back to fetch only if a network is available."""
    d = ROOT / "data" / "repos" / repo.replace("/", "__")
    if not d.exists():
        if subprocess.run(["git", "clone", "--quiet", f"https://github.com/{repo}", str(d)]).returncode != 0:
            return None
    if subprocess.run(["git", "-C", str(d), "checkout", "--quiet", sha], capture_output=True).returncode != 0:
        subprocess.run(["git", "-C", str(d), "fetch", "--quiet", "origin", sha], capture_output=True)
        if subprocess.run(["git", "-C", str(d), "checkout", "--quiet", sha], capture_output=True).returncode != 0:
            return None
    return d
