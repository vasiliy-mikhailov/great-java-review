"""Replace each early bundle's truncated diff with the FULL PR diff — read-only.

Uses `git diff <base_sha>...pr-<pr>-head` against the already-fetched local branch:
NO checkout (won't disturb the running container's working tree) and NO fetch (won't
violate the single-GitHub-worker rule P5). Same 150k cap + explicit truncation marker
as the harness, so 'truncated' is never mistaken for 'absent'.

  python3 src/enrich_bundles_fulldiff.py
"""
from __future__ import annotations
import glob, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from current_version.full_diff import TRUNC_MARK  # noqa: E402

BUNDLE_DIR = "results/claude_judge"
REPOS = "data/repos"
CACHE = "results/base_sha_cache.json"
MAX = 150000


def main():
    base = json.load(open(CACHE))
    enriched, skipped = [], []
    for f in sorted(glob.glob(f"{BUNDLE_DIR}/early_*.json")):
        b = json.load(open(f))
        repo, pr = b["repo"], b["pr"]
        d = f"{REPOS}/{repo.replace('/', '__')}"
        bsha = base.get(f"{repo}#{pr}")
        if not bsha or not os.path.isdir(d):
            skipped.append((pr, "no-sha-or-repo")); continue
        ref = f"pr-{pr}-head"
        # confirm the local branch exists (no fetch); else skip (keep truncated)
        chk = subprocess.run(["git", "-C", d, "rev-parse", "--verify", "--quiet", ref],
                             capture_output=True, text=True)
        if chk.returncode != 0:
            skipped.append((pr, "no-local-pr-branch")); continue
        r = subprocess.run(["git", "-C", d, "diff", f"{bsha}...{ref}"],
                           capture_output=True, text=True, timeout=300)
        diff = r.stdout if r.stdout.strip() else None
        if not diff:
            skipped.append((pr, "empty-diff")); continue
        header = (b.get("diff", "") or "")[:1200]
        body = header + "\n\nFULL DIFF:\n" + diff
        if len(body) > MAX:
            keep = body[:MAX]; keep = keep[: keep.rfind("\n") + 1]
            body = keep + TRUNC_MARK.format(more=len(body) - len(keep))
        b["diff"] = body
        b["diff_full"] = True
        json.dump(b, open(f, "w"), indent=1)
        enriched.append((pr, len(diff)))
    print(f"enriched {len(enriched)}: {[(p, f'{n//1000}k') for p, n in enriched]}")
    if skipped:
        print(f"skipped {len(skipped)}: {skipped}")


if __name__ == "__main__":
    main()
