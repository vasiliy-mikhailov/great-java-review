"""`search` — the intent-perfect replacement for the filename-only `grep`.

Traces show the subagents' dominant intent is "show me the actual lines of code for
symbol/pattern X" (read a method body, a config block, a usage). The stock `grep` runs
`rg -l` (FILE NAMES only) and refuses a single-file path, forcing a grep->view-whole-file
->page loop of 15-26 calls. `search` returns the MATCHING LINES with surrounding context
(`file:line: code`), accepts a single FILE or a dir, and takes repo-relative paths — so
the same intent is satisfied in ONE call.

Smoke:  ./venv-oh/bin/python -u src/search_tool.py <repo_dir> <pattern> [path] [include]
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


class SearchAction(Action):
    pattern: str = Field(description="Regex to search file CONTENTS for (case-insensitive).")
    path: str | None = Field(
        default=None,
        description="File OR directory to search — repo-relative (e.g. 'pom.xml', "
        "'src/main/java/.../Foo.java') or absolute. Unlike grep, a single FILE is "
        "allowed. Defaults to the repo root.",
    )
    include: str | None = Field(
        default=None, description='Optional glob filter, e.g. "*.java", "pom.xml".')
    context: int = Field(
        default=3, description="Lines of surrounding context around each match (grep -C).")


class SearchObservation(Observation):
    pattern: str = Field(default="")


TOOL_DESCRIPTION = """Content search that returns the MATCHING LINES with surrounding \
context (like `grep -n -C`), not just file names.
* Returns `path:line: code` for each hit plus `context` lines around it — so you SEE the \
code without opening the file.
* `path` may be a single FILE or a directory, repo-relative or absolute.
* Use this to read a method body, a config block, or a symbol's definition/usages in ONE \
call instead of grep-then-view.
* Output is capped; narrow with a stricter pattern, an `include` glob, or a file `path`.
"""


class SearchExecutor(ToolExecutor):
    _MAX_CHARS = 12000

    def __init__(self, working_dir: str):
        self.working_dir = os.path.realpath(working_dir)

    def _target(self, path: str | None) -> str:
        if not path:
            return "."
        if os.path.isabs(path):
            try:
                rel = os.path.relpath(os.path.realpath(path), self.working_dir)
                if not rel.startswith(".."):
                    return rel
            except Exception:  # noqa: BLE001
                pass
            return path
        return path

    def __call__(self, action: SearchAction, conversation: "LocalConversation | None" = None):  # noqa: ARG002
        target = self._target(action.path)
        abs = target if os.path.isabs(target) else os.path.join(self.working_dir, target)
        if action.path and not os.path.exists(abs):
            return SearchObservation.from_text(
                text=(f"Path '{action.path}' does not exist at the base commit. "
                      "NOTE: files ADDED or RENAMED by this PR are NOT on disk yet "
                      "(the repo is checked out at the PR's base) — don't search for "
                      "them; read them from the diff instead."),
                pattern=action.pattern, is_error=True)
        ctx = max(0, min(int(action.context), 20))
        cmd = ["rg", "-n", "-i", "--no-heading", "--color", "never", "-C", str(ctx)]
        if action.include:
            cmd += ["-g", action.include]
        cmd += ["-e", action.pattern, target]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               check=False, cwd=self.working_dir)
        except Exception as e:  # noqa: BLE001
            return SearchObservation.from_text(text=f"search error: {e}",
                                               pattern=action.pattern, is_error=True)
        out = r.stdout or ""
        if not out.strip():
            where = f" in '{action.path}'" if action.path else ""
            filt = f" (filter {action.include})" if action.include else ""
            return SearchObservation.from_text(
                text=f"No matches for /{action.pattern}/{where}{filt}.",
                pattern=action.pattern)
        truncated = False
        if len(out) > self._MAX_CHARS:
            out = out[: self._MAX_CHARS]
            out = out[: out.rfind("\n") + 1]
            truncated = True
        nlines = out.count("\n")
        header = f"{nlines} line(s) (matches + {ctx} context) for /{action.pattern}/:\n"
        if truncated:
            out += "\n[truncated — narrow the pattern, add an include glob, or pass a file path]"
        return SearchObservation.from_text(text=header + out, pattern=action.pattern)


class SearchTool(ToolDefinition[SearchAction, SearchObservation]):
    def declared_resources(self, action: Action) -> DeclaredResources:
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state: "ConversationState") -> Sequence["SearchTool"]:
        wd = conv_state.workspace.working_dir
        if not os.path.isdir(wd):
            raise ValueError(f"working_dir '{wd}' is not a valid directory")
        desc = (f"{TOOL_DESCRIPTION}\n\nYour working directory is: {wd}\n"
                "Repo-relative paths are resolved against it.")
        return [cls(
            description=desc, action_type=SearchAction, observation_type=SearchObservation,
            annotations=ToolAnnotations(title="search", readOnlyHint=True,
                                        destructiveHint=False, idempotentHint=True,
                                        openWorldHint=False),
            executor=SearchExecutor(wd))]


try:
    register_tool("search", SearchTool)
except Exception:  # noqa: BLE001
    pass


if __name__ == "__main__":   # standalone smoke (no Conversation needed)
    import sys
    wd = sys.argv[1]
    pat = sys.argv[2] if len(sys.argv) > 2 else "spotless-maven-plugin"
    path = sys.argv[3] if len(sys.argv) > 3 else None
    inc = sys.argv[4] if len(sys.argv) > 4 else None
    ex = SearchExecutor(wd)
    obs = ex(SearchAction(pattern=pat, path=path, include=inc, context=3))
    print(obs.text)
