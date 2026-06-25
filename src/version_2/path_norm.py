"""Path normalization for grep / glob / file_editor (v4, W-fix #1).

Trace analysis (37 PRs): 62% of subagent sessions lose turns to path-format flailing —
"I need the absolute path", "path doesn't exist, let me check the repo structure" — because
`search` accepts repo-relative paths while file_editor demands absolute and grep/glob are
inconsistent. Each recovery turn re-sends the full ~25-70k context.

Fix: wrap the three executors so any path the agent passes is resolved against, in order:
as-given, the tool's working dir (repo root), the process CWD, and (for wrong-absolute
paths like "/data/repos/...") the same candidates with the leading slash stripped. First
existing candidate wins; otherwise fall back to repo-root-relative. Pure widening — every
previously-valid path still works.

Enable with path_norm.install() (idempotent).
"""
from __future__ import annotations

import os

_installed = False


def _norm(p, wd):
    if not p:
        return p
    cands = []
    if os.path.isabs(p):
        if os.path.exists(p):
            return p
        stripped = p.lstrip("/")
        cands = [os.path.join(wd, stripped), os.path.join(os.getcwd(), stripped)]
    else:
        cands = [os.path.join(wd, p), os.path.join(os.getcwd(), p), p]
    for c in cands:
        if os.path.exists(c):
            return os.path.abspath(c)
    return p if os.path.isabs(p) else os.path.join(wd, p)


def _patched(orig, get_wd):
    def call(self, action, conversation=None):
        p = getattr(action, "path", None)
        if p:
            try:
                np_ = _norm(str(p), str(get_wd(self)))
                if np_ != str(p):
                    action = action.model_copy(update={"path": np_})
            except Exception:  # noqa: BLE001  never break the tool over normalization
                pass
        return orig(self, action, conversation)
    return call


def install():
    global _installed
    if _installed:
        return
    from openhands.tools.grep.impl import GrepExecutor
    from openhands.tools.glob.impl import GlobExecutor
    from openhands.tools.file_editor.impl import FileEditorExecutor
    GrepExecutor.__call__ = _patched(GrepExecutor.__call__,
                                     lambda s: getattr(s, "working_dir", os.getcwd()))
    GlobExecutor.__call__ = _patched(GlobExecutor.__call__,
                                     lambda s: getattr(s, "working_dir", os.getcwd()))
    FileEditorExecutor.__call__ = _patched(
        FileEditorExecutor.__call__,
        lambda s: getattr(getattr(s, "editor", None), "workspace_root", None) or os.getcwd())
    _installed = True
