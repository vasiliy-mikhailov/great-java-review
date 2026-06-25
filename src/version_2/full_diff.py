"""v5 fix #1 — the FULL PR diff instead of the dataset's 7k-char truncation.

Claude judging traced ~60% of fabrications to one pipeline: the truncated diff omits
hunks -> the reviewer "verifies" their absence against the BASE repo (which confirms it
by definition) -> confident false "X was not updated" findings. This module rebuilds the
PR input with the complete diff from git history (`git fetch origin pull/N/head` works
for any merged or open PR), and when the diff still exceeds the budget it marks the cut
EXPLICITLY so no one can mistake truncation for absence.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

TRUNC_MARK = ("\n\n<<< DIFF TRUNCATED HERE — the pull request continues beyond this point "
              "({more:,} more characters not shown). Content not visible above may still "
              "exist in the PR; never report something as missing or not-updated unless "
              "the visible diff proves it. >>>\n")


def _run(args, cwd=None, timeout=120):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def full_pr_diff(repo_dir, repo, pr, base_sha):
    """Return the complete unified diff of the PR, or None on failure."""
    d = str(Path(repo_dir))
    # the PR head ref is exposed by GitHub for every PR
    head = f"refs/pull/{pr}/head"
    local = f"pr-{pr}-head"
    r = _run(["git", "-C", d, "fetch", "--quiet", "origin", f"pull/{pr}/head:{local}"],
             timeout=300)
    target = local if r.returncode == 0 else None
    if target is None:                      # fallback: merge commit already in history
        r = _run(["git", "-C", d, "log", "--all", "--format=%H", "--grep",
                  f"#{pr}", "-1"])
        target = r.stdout.strip() or None
    if target is None:
        return None
    r = _run(["git", "-C", d, "diff", f"{base_sha}...{target}"], timeout=300)
    if r.returncode != 0 or not r.stdout.strip():
        r = _run(["git", "-C", d, "diff", f"{base_sha}..{target}"], timeout=300)
    return r.stdout if r.stdout.strip() else None


def full_pr_input(base_input, repo_dir, repo, pr, base_sha, max_chars=150000):
    """Rebuild pr_input: keep the dataset header, replace the truncated diff with the
    full one. If the full diff exceeds the budget, cut WITH an explicit marker."""
    diff = full_pr_diff(repo_dir, repo, pr, base_sha)
    if not diff:
        return base_input, False           # fall back to dataset input unchanged
    head, sep, _ = base_input.partition("DIFF:\n")
    if not sep:
        head = base_input[:1500] + "\n"
    body = head + "DIFF:\n" + diff
    if len(body) > max_chars:
        keep = body[:max_chars]
        keep = keep[: keep.rfind("\n") + 1]
        body = keep + TRUNC_MARK.format(more=len(body) - len(keep))
    return body, True
