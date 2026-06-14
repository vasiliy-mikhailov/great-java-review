"""OpenHands delegation reviewer — the engine.

An ORCHESTRATOR decomposes the PR into investigation subtasks and DELEGATES each to a
read-only subagent, so no single context has to hold the whole repo. Each subagent runs in
its own context and returns a grounded finding; the orchestrator synthesizes the review.

Two subagent roles:
  - code-explorer: leaf reader (search/grep/glob/file_editor + the pr tools), answers ONE
    question precisely.
  - investigator: a substantial area; reads, and may sub-delegate to code-explorer (depth-2).

The model-facing prompts live in prompts.py. This module is the machinery: context assembly,
compaction, subagent registration, the orchestrator loop, and review extraction.

  ./venv-oh/bin/python src/v8/harness.py <repo_dir> <repo> <pr>
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ on path
from v8.llm import _llm, _to_text, _post_think  # noqa: E402
from v8.prompts import ORCH_SYS, INVESTIGATOR_SYS, CODE_EXPLORER_SYS, SUB_GUIDE, SYNTHESIS_GUIDE  # noqa: E402
from llm_client import final_review  # noqa: E402


# --- review extraction ------------------------------------------------------------------

_REVIEW_RE = re.compile(r"<review>(.*?)</review>", re.DOTALL | re.IGNORECASE)


def _tagged(text: str) -> str:
    """Pull the review out of <review>...</review>. Robust to where the model put it
    (finish message vs its thought) and to a truncated/unclosed tag."""
    if not text:
        return ""
    ms = _REVIEW_RE.findall(text)
    if ms:
        return ms[-1].strip()
    low = text.lower()
    if "<review>" in low:                      # unclosed (truncated) — take the tail
        return text[low.rfind("<review>") + len("<review>"):].replace("</review>", "").strip()
    return ""


def dump_events(conv, path):
    """Serialize the full event log (orchestrator + subagents, with thoughts, tool calls,
    grep output, file reads) to JSON for analysis. Best-effort: never break a rollout."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out = []
        for e in conv.state.events:
            try:
                out.append({"type": type(e).__name__, **e.model_dump(mode="json")})
            except Exception:  # noqa: BLE001
                out.append({"type": type(e).__name__, "repr": str(e)[:4000]})
        json.dump(out, open(path, "w"), indent=1, default=str)
    except Exception:  # noqa: BLE001
        pass


from openhands.sdk import Agent, Conversation, register_tool, Tool  # noqa: E402
from openhands.sdk import LLMSummarizingCondenser  # noqa: E402
from openhands.sdk.subagent.registry import register_agent_if_absent  # noqa: E402
from openhands.sdk.event import ActionEvent, MessageEvent  # noqa: E402
from openhands.sdk.conversation.visualizer.base import ConversationVisualizerBase  # noqa: E402
from openhands.tools.preset.default import get_default_tools  # noqa: E402
from openhands.tools.grep import GrepTool  # noqa: E402
from openhands.tools.glob import GlobTool  # noqa: E402
from openhands.tools.file_editor import FileEditorTool  # noqa: E402
from v8 import search_tool  # noqa: E402,F401  registers the "search" tool (ripgrep + context)
from v8 import path_norm  # noqa: E402
path_norm.install()                          # normalize tool path args (abs/.. -> repo-relative)


def extract_review(events) -> str:
    """Pull the final review text out of an orchestrator conversation's events.

    The review lives in the finish action. Combine its thought THEN message so _tagged's
    ms[-1] returns the GLOBALLY LAST <review> (the model often drafts <review> several times
    while reasoning; the real one is last). The finish tool nests its message under
    `action.message` — model_dump().get("message") is None, so read action.message too.
    Falls back to the latest agent message, then to the most review-like text."""
    finish_text = ""
    for a in reversed([e for e in events if isinstance(e, ActionEvent)]):
        if getattr(a, "tool_name", None) == "finish":
            try:
                d = a.model_dump()
                msg = d.get("message")
                if msg is None:
                    msg = (d.get("action") or {}).get("message")
                finish_text = (_to_text(d.get("thought")) + "\n" + _to_text(msg))
            except Exception:  # noqa: BLE001
                pass
            break
    amsgs = [e for e in events if isinstance(e, MessageEvent)
             and getattr(e, "source", None) == "agent"]
    msgs = []
    for m in amsgs[-3:]:
        try:
            msgs.append(_to_text([getattr(c, "text", "") for c in m.llm_message.content]))
        except Exception:  # noqa: BLE001
            pass
    # 1) LAST <review>...</review> — finish turn first, then the latest agent msg.
    for src in [finish_text] + msgs[::-1]:
        t = _tagged(src)
        if t:
            return t
    # 2) no tags -> the candidate that most looks like a review (SUMMARY:/POINTS:, else the
    #    longest post-think text). Handles the review-in-`thought` case.
    cand = [c for c in ([finish_text] + msgs) if c and c.strip()]
    if cand:
        return max(cand, key=lambda t: (("SUMMARY:" in t or "POINTS:" in t),
                                        len(_post_think(t))))
    return ""


# Force the SUBPROCESS terminal backend instead of tmux. The tmux backend opens a
# pane/window per subagent terminal via a pool; at scale (many rollouts x 10-15 subagents,
# depth-2) it exhausts PTYs/forks -> "fork failed: Device not configured" -> subagent tasks
# fail -> rollouts score 0.0 and the run dies. Subprocess terminals use pipes (cheap).
try:
    import openhands.tools.terminal.impl as _t_impl  # noqa: E402
    import openhands.tools.terminal.terminal.factory as _t_fac  # noqa: E402
    _t_impl._is_tmux_available = lambda: False
    _t_fac._is_tmux_available = lambda: False
except Exception:  # noqa: BLE001
    pass


class _NoViz(ConversationVisualizerBase):
    """Disable OpenHands' Rich console visualizer. It does BLOCKING writes to the
    (redirected) stdout for every event; in a long batch run the pipe buffer fills and
    `console.print` raises -> every rollout instant-fails. We don't need the pretty output."""

    def on_event(self, event):
        return None

    def create_sub_visualizer(self, *a, **k):   # subagent conversations stay quiet too
        return self


def _changed_files_content(repo_dir, pr_input, max_chars=240000):   # ~64k tokens
    """Read the full BASE content of the PR's changed files and return it as a block, so the
    ORCHESTRATOR has the changed files directly in context. New files don't exist at base
    (they're additions in the diff) -> noted. Capped for huge PRs (then fall back to tools)."""
    m = re.search(r"Changed files \(\d+\):\s*(.+)", pr_input)
    if not m:
        return ""
    files = [f.strip() for f in m.group(1).split(",") if f.strip()]
    blocks, total = [], 0
    for f in files:
        p = os.path.join(str(repo_dir), f)
        if not os.path.isfile(p):
            blocks.append(f"### {f}\n(added by this PR — not present at base; see the diff)")
            continue
        try:
            txt = open(p, errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        block = f"### {f}\n{txt}"
        if total + len(block) > max_chars:
            blocks.append(f"(… {len(files) - len(blocks)} more changed files omitted for "
                          "size; use grep/glob/file_editor for those)")
            break
        blocks.append(block); total += len(block)
    return "\n\n".join(blocks)


def _condenser(llm):
    """OpenHands context compaction (same Qwen model). Once history crosses max_tokens,
    older events are replaced by a summary, so the orchestrator's synthesis context can't
    bloat until Qwen 'gives up' (emits </think> then nothing -> empty review -> 0.0).

    keep_first pins the opening events: the PR/diff is the orchestrator's first user message
    (event idx 1, right after the system prompt), so keep_first must comfortably cover it,
    else the condenser could summarize the PR away and synthesis would run blind.

    INVARIANT: max_tokens + agent.max_output_tokens <= max-model-len (vLLM ERRORS if
    prompt + requested output > 262144). With output capped at 131072, the ceiling is 131072;
    120000 leaves margin for the system prompt + tool schemas. If max_output_tokens changes,
    move this. max_size=240 is a harmless high event-count backstop; the token trigger fires first.

    The condenser LLM clones the model with thinking OFF: a thinking summarizer pours its
    chain-of-thought into the summary (~4.5k chars to summarize one sentence in testing),
    which INVERTS compaction (the summary grows the context instead of shrinking it).
    """
    cond_llm = llm.model_copy(update={
        "usage_id": "oh_condenser",
        "litellm_extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    })
    return LLMSummarizingCondenser(llm=cond_llm, max_size=240, keep_first=6,
                                   max_tokens=120000)


MAX_ORCH_STEPS = 24       # runaway backstop on orchestrator actions; not a quality budget


_CURRENT_PR = {"input": "", "sub": ""}   # set per rollout; subagent factories read it at spawn time
_SUBAGENTS_READY = False


def _register_subagents():
    # idempotent (register_*_if_absent + guard) — called once per rollout.
    global _SUBAGENTS_READY
    if _SUBAGENTS_READY:
        return
    from v8.search_tool import SearchTool
    from v8.pr_diff_tool import PrFilesTool, PrFileDiffTool
    for n, cls in (("grep", GrepTool), ("glob", GlobTool), ("file_editor", FileEditorTool),
                   ("search", SearchTool), ("pr_files", PrFilesTool),
                   ("pr_file_diff", PrFileDiffTool)):
        try:
            register_tool(n, cls)
        except Exception:  # noqa: BLE001  (already registered)
            pass
    read_tools = [Tool(name="search"), Tool(name="grep"), Tool(name="glob"),
                  Tool(name="file_editor"), Tool(name="pr_files"), Tool(name="pr_file_diff")]
    task_spec = [t for t in get_default_tools(enable_browser=False, enable_sub_agents=True)
                 if getattr(t, "name", None) == "task_tool_set"]

    def _with_pr(base_sys):
        # Lean subagent context: the diff + the complete changed-file list, NOT the base file
        # bodies (those are one file_editor/search call away). Frees the window for investigation.
        return (base_sys + SUB_GUIDE
                + "\n\n--- PULL REQUEST (title + complete changed-file list + diff; base "
                  "content of any file is on disk — read it with tools) ---\n"
                + (_CURRENT_PR.get("sub") or _CURRENT_PR["input"])[:240000])

    # Subagents carry a big system prompt (diff + changed-file list); cap their OUTPUT so
    # input + output stays under the 262k max-model-len. They return findings, not full reviews.
    def _sub_llm(llm):
        return llm.model_copy(update={"usage_id": "oh_subagent", "max_output_tokens": 32768})

    def code_explorer_factory(llm):              # leaf, read-only, NO terminal/PTY
        sl = _sub_llm(llm)
        return Agent(llm=sl, tools=list(read_tools), system_prompt=_with_pr(CODE_EXPLORER_SYS),
                     condenser=_condenser(sl))

    def investigator_factory(llm):               # depth-2: read + sub-delegate, NO PTY
        sl = _sub_llm(llm)
        return Agent(llm=sl, tools=read_tools + task_spec, system_prompt=_with_pr(INVESTIGATOR_SYS),
                     condenser=_condenser(sl))

    register_agent_if_absent("code-explorer", code_explorer_factory,
                             "Read-only Java investigator (search/grep/glob/file_editor, no shell); "
                             "answers ONE question with a precise grounded finding.")
    register_agent_if_absent("investigator", investigator_factory,
                             "Investigates one area; may sub-delegate to code-explorer "
                             "(depth-2). No shell.")
    _SUBAGENTS_READY = True


def mr_code_review(repo_dir, pr_input, profile="qwen"):
    """MR + code (NO tools): a single LLM call with the diff AND the full changed-file bodies in
    context, but no grep/glob/file_editor and no delegation. The middle rung between diff-only
    and the full tool-using delegation harness (isolates the value of having the whole files)."""
    from llm_client import get_llm, final_review
    files = _changed_files_content(repo_dir, pr_input)
    ctx = pr_input + (("\n\n=== FULL CONTENT OF THE CHANGED FILES (base commit) — review "
                       "these directly ===\n" + files) if files else "")
    llm = get_llm(profile)
    sysp = ("You are an expert Java code reviewer. Below is the PR diff AND the full content "
            "of the changed files at the base commit. Review the change directly using that "
            "context. Output SUMMARY: then POINTS: with file-anchored points.")
    return final_review(llm.complete(sysp, "PULL REQUEST:\n" + ctx + "\n\nWrite the review."))


def oh_review_delegate(repo_dir, pr_input, profile="qwen", max_steps=MAX_ORCH_STEPS,
                       policy=None, trace_path=None):
    """policy = the orchestrator system prompt override (the GEPA genome). Defaults to ORCH_SYS.
    trace_path: if set, dump the full orchestrator+subagent event log there for analysis."""
    _files = _changed_files_content(repo_dir, pr_input)
    ctx = pr_input + (("\n\n=== FULL CONTENT OF THE CHANGED FILES (base commit) — you "
                       "ALREADY HAVE these in context; review them DIRECTLY and do NOT "
                       "re-read them with tools. Use grep/glob/file_editor only for SURROUNDING "
                       "code (callers, conventions, existing impls elsewhere). ===\n"
                       + _files) if _files else "")
    _CURRENT_PR["input"] = ctx        # orchestrator gets diff + full changed files
    _CURRENT_PR["sub"] = pr_input     # subagents get the diff only (lean context)
    _register_subagents()             # code-explorer (leaf) + investigator (depth-2 capable)
    llm = _llm(profile)
    all_tools = get_default_tools(enable_browser=False, enable_sub_agents=True)
    orch_tools = [t for t in all_tools
                  if getattr(t, "name", None) in ("task_tool_set", "task_tracker")]
    orch_sys = (policy or ORCH_SYS) + SYNTHESIS_GUIDE
    agent = Agent(llm=llm, tools=orch_tools, system_prompt=orch_sys,
                  condenser=_condenser(llm))

    state = {"n": 0, "conv": None, "capped": False}

    def _cap(ev):
        if isinstance(ev, ActionEvent):
            state["n"] += 1
            if state["n"] >= max_steps and state["conv"] is not None:
                state["capped"] = True
                try:
                    state["conv"].pause()
                except Exception:  # noqa: BLE001
                    pass

    conv = Conversation(agent=agent, workspace=str(repo_dir), callbacks=[_cap],
                        visualizer=_NoViz,
                        persistence_dir=(os.environ.get("OH_PERSIST") or None))
    state["conv"] = conv

    try:
        conv.send_message("PULL REQUEST UNDER REVIEW:\n" + _CURRENT_PR["input"] +
                          "\n\nDelegate the investigation, then write the review.")
        conv.run()
        raw = extract_review(conv.state.events)
        if "SUMMARY:" not in raw and "POINTS:" not in raw and len(_post_think(raw)) < 200:
            state["n"] = 0
            try:
                conv.send_message("Stop delegating. Write the final review NOW, wrapped "
                                  "in <review></review> tags: <review>SUMMARY: <para> "
                                  "POINTS: - [File.java:line] <point></review>")
                conv.run()
                raw = extract_review(conv.state.events) or raw
            except Exception:  # noqa: BLE001
                pass
        if os.environ.get("OH_DEBUG"):
            print(">>> RAW(last400):", repr(raw[-400:]), flush=True)
            n = 0
            for e in conv.state.events:                 # dump subagent findings (task results)
                if type(e).__name__ in ("ObservationEvent",) and n < 8:
                    try:
                        d = e.model_dump()
                        txt = _to_text(d.get("content") or d.get("observation") or d)
                        if txt.strip():
                            print(f">>> FINDING[{n}]:", repr(txt[:240]), flush=True); n += 1
                    except Exception:  # noqa: BLE001
                        pass
        review = final_review(_post_think(raw))
        trace = []
        for a in conv.state.events:
            if isinstance(a, ActionEvent):
                name = getattr(a, "tool_name", type(a).__name__)
                arg = ""
                try:
                    d = a.model_dump()
                    arg = str(d.get("prompt") or d.get("description") or d.get("command") or "")[:90]
                except Exception:  # noqa: BLE001
                    pass
                trace.append((f"{name} {arg}".strip(), ""))
        return review, trace
    finally:
        if trace_path:                       # full event log (runs even on cap/exception)
            dump_events(conv, trace_path)
        # CRITICAL: release the conversation's terminal sessions (orchestrator AND subagents).
        # Without this they leak across rollouts until the OS can't fork -> rollouts hit 0.0.
        # close() cascades to sub-conversations via the TaskManager.
        try:
            conv.close()
        except Exception:  # noqa: BLE001
            pass


def run(repo_dir, repo, pr, profile="qwen"):
    import dataset as ds
    import metric as mt
    inst = ds.build_instances()
    rv = next((x for v in inst.values() for x in v
               if x["repo"] == repo and str(x["pr"]) == str(pr)), None)
    if not rv:
        print(f"{repo}#{pr} not found"); return
    print(f"=== OpenHands DELEGATION: {repo}#{pr} ({rv['reviewer']}) ===", flush=True)
    review, trace = oh_review_delegate(repo_dir, rv["input"], profile)
    score, _ = mt.score_with_feedback(rv["input"], review, rv["reference_review"], profile)
    print("DELEGATIONS/actions:", [t for t, _ in trace])
    print("REVIEW:\n", review[:1400])
    print(f"\nSCORE vs human = {score:.3f}  ({len(trace)} orchestrator actions)")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]),
        sys.argv[4] if len(sys.argv) > 4 else "qwen")
