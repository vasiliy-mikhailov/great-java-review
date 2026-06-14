"""v6 — `pr_files` + `pr_file_diff`: the PR itself as a queryable object.

v5 inlines the full diff but still truncates at 150k chars (2/37 PRs hit it; both were
v5's weakest wins), and subagents only ever see the prompt's possibly-cut copy. The PR
head ref is already fetched locally (full_diff.py), so git can answer precisely:
  pr_files      -> every file the PR touches (status + line counts), never truncated
  pr_file_diff  -> the COMPLETE unified diff of ONE file, straight from git

Per-PR context (repo_dir, base sha, head ref) is set by the runner via set_pr(),
mirroring oh_delegate's _CURRENT_PR pattern (one PR at a time per process).

Smoke:  ./venv-oh/bin/python -u src/pr_diff_tool.py <repo_dir> <base_sha> <pr> [file]
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)

if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.conversation import LocalConversation

# set by the runner before each PR's review (sequential, one PR per process at a time)
_PR_CTX = {"repo_dir": None, "base": None, "target": None}


def _git(repo_dir, *args, timeout=60):
    return subprocess.run(["git", "-C", str(repo_dir), *args],
                          capture_output=True, text=True, timeout=timeout, check=False)


def resolve_target(repo_dir, pr):
    """The PR head: the local branch full_diff.py fetched, else a merge commit."""
    local = f"pr-{pr}-head"
    if _git(repo_dir, "rev-parse", "--verify", "--quiet", local).returncode == 0:
        return local
    r = _git(repo_dir, "log", "--all", "--format=%H", "--grep", f"#{pr}", "-1")
    return r.stdout.strip() or None


def set_pr(repo_dir, base_sha, pr):
    _PR_CTX["repo_dir"] = str(repo_dir)
    _PR_CTX["base"] = base_sha
    _PR_CTX["target"] = resolve_target(repo_dir, pr)
    return _PR_CTX["target"]


def _ready():
    if not (_PR_CTX["repo_dir"] and _PR_CTX["base"] and _PR_CTX["target"]):
        return ("The PR's git history is not available in this checkout, so this tool "
                "cannot answer — rely on the diff text in your context instead.")
    return None


def changed_files():
    """Complete changed-file paths from git (v7: replaces the dataset header's
    silently-[:25]-capped list). Requires set_pr() to have been called."""
    if _ready():
        return []
    r = _git(_PR_CTX["repo_dir"], "diff", "--name-only", "-M",
             f"{_PR_CTX['base']}...{_PR_CTX['target']}")
    return [l for l in r.stdout.splitlines() if l.strip()]


# ---------------------------------------------------------------- pr_files
class PrFilesAction(Action):
    pass


class PrFilesObservation(Observation):
    pass


PR_FILES_DESC = """List EVERY file changed by this pull request — complete, straight \
from git, even when the diff text in your context is truncated.
* One line per file: status (A added / M modified / D deleted / R renamed), \
+added/-deleted line counts, and the path to pass to `pr_file_diff`.
* Takes no arguments."""


class PrFilesExecutor(ToolExecutor):
    def __call__(self, action: PrFilesAction, conversation: "LocalConversation | None" = None):  # noqa: ARG002
        err = _ready()
        if err:
            return PrFilesObservation.from_text(text=err, is_error=True)
        d, rng = _PR_CTX["repo_dir"], f"{_PR_CTX['base']}...{_PR_CTX['target']}"
        st = _git(d, "diff", "--name-status", "-M", rng)
        num = _git(d, "diff", "--numstat", "-M", rng)
        if st.returncode != 0 or not st.stdout.strip():
            return PrFilesObservation.from_text(
                text=f"git diff failed for {rng}: {st.stderr.strip() or 'empty diff'}",
                is_error=True)
        counts = {}
        for line in num.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                counts[parts[-1]] = (parts[0], parts[1])
        rows = []
        for line in st.stdout.splitlines():
            parts = line.split("\t")
            status, path = parts[0], parts[-1]
            a, r = counts.get(path, ("?", "?"))
            old = f"  (was {parts[1]})" if status.startswith("R") and len(parts) == 3 else ""
            rows.append(f"{status[0]:2} +{a:>5} -{r:>5}  {path}{old}")
        body = "\n".join(rows)
        return PrFilesObservation.from_text(
            text=f"{len(rows)} file(s) changed by this PR (full list):\n{body}")


class PrFilesTool(ToolDefinition[PrFilesAction, PrFilesObservation]):
    def declared_resources(self, action: Action) -> DeclaredResources:
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state: "ConversationState") -> Sequence["PrFilesTool"]:
        return [cls(
            description=PR_FILES_DESC, action_type=PrFilesAction,
            observation_type=PrFilesObservation,
            annotations=ToolAnnotations(title="pr_files", readOnlyHint=True,
                                        destructiveHint=False, idempotentHint=True,
                                        openWorldHint=False),
            executor=PrFilesExecutor())]


# ---------------------------------------------------------------- pr_file_diff
class PrFileDiffAction(Action):
    path: str = Field(description="Repo-relative path of ONE changed file, exactly as "
                                  "listed by `pr_files` (e.g. 'src/main/java/.../Foo.java').")


class PrFileDiffObservation(Observation):
    path: str = Field(default="")


PR_FILE_DIFF_DESC = """The COMPLETE unified diff this pull request makes to ONE file, \
straight from git — including any part cut from the diff text in your context.
* Use the exact path from `pr_files`.
* Whatever this returns is the whole change to that file: it is safe to state that \
something absent here is absent from the PR's change to THIS file."""

_MAX_CHARS = 40000
_CUT = ("\n<<< diff for this file truncated here — {more:,} more characters. The part "
        "shown is exact and complete up to the cut; do not claim anything about the "
        "unseen remainder. >>>\n")


class PrFileDiffExecutor(ToolExecutor):
    def __call__(self, action: PrFileDiffAction, conversation: "LocalConversation | None" = None):  # noqa: ARG002
        err = _ready()
        if err:
            return PrFileDiffObservation.from_text(text=err, path=action.path, is_error=True)
        d, rng = _PR_CTX["repo_dir"], f"{_PR_CTX['base']}...{_PR_CTX['target']}"
        path = action.path.lstrip("/")
        r = _git(d, "diff", "-M", rng, "--", path)
        if r.returncode != 0:
            return PrFileDiffObservation.from_text(
                text=f"git diff failed: {r.stderr.strip()}", path=path, is_error=True)
        out = r.stdout
        if not out.strip():
            return PrFileDiffObservation.from_text(
                text=(f"This PR makes no change to '{path}' (or the path is misspelled "
                      "— call `pr_files` for the exact list)."), path=path)
        if len(out) > _MAX_CHARS:
            keep = out[:_MAX_CHARS]
            keep = keep[: keep.rfind("\n") + 1]
            out = keep + _CUT.format(more=len(r.stdout) - len(keep))
        return PrFileDiffObservation.from_text(
            text=f"Complete PR diff for {path}:\n{out}", path=path)


class PrFileDiffTool(ToolDefinition[PrFileDiffAction, PrFileDiffObservation]):
    def declared_resources(self, action: Action) -> DeclaredResources:
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state: "ConversationState") -> Sequence["PrFileDiffTool"]:
        return [cls(
            description=PR_FILE_DIFF_DESC, action_type=PrFileDiffAction,
            observation_type=PrFileDiffObservation,
            annotations=ToolAnnotations(title="pr_file_diff", readOnlyHint=True,
                                        destructiveHint=False, idempotentHint=True,
                                        openWorldHint=False),
            executor=PrFileDiffExecutor())]


for _n, _cls in (("pr_files", PrFilesTool), ("pr_file_diff", PrFileDiffTool)):
    try:
        register_tool(_n, _cls)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":   # standalone smoke (no Conversation needed)
    import sys
    d, bsha, pr = sys.argv[1], sys.argv[2], sys.argv[3]
    tgt = set_pr(d, bsha, pr)
    print(f"target: {tgt}\n")
    print(PrFilesExecutor()(PrFilesAction()).text[:3000])
    if len(sys.argv) > 4:
        print()
        print(PrFileDiffExecutor()(PrFileDiffAction(path=sys.argv[4])).text[:3000])
