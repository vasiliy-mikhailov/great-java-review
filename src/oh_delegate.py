"""OpenHands DELEGATION-based reviewer (Attempt 3, the right shape).

Instead of one agent reading every file until context blows up, an ORCHESTRATOR
decomposes the PR into investigation subtasks and DELEGATES each to a read-only
`java-investigator` subagent (native OpenHands `task` tool). Each subagent runs in
its OWN context and returns only a concise grounded finding, so the orchestrator's
context stays lean -> no blowup, no lost-in-the-middle, clean final generation.

  ./venv-oh/bin/python src/oh_delegate.py <repo_dir> <repo> <pr>
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

sys.path.insert(0, os.path.dirname(__file__))
from oh_review import _llm, _to_text, _post_think  # noqa: E402  reuse
from llm_client import final_review  # noqa: E402


def dump_events(conv, path):
    """Serialize the FULL event log (every MessageEvent/ActionEvent/ObservationEvent —
    orchestrator AND subagents, with thoughts, tool calls, grep output, file reads) to
    JSON for future analysis. Best-effort: never let trace-saving break a rollout."""
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

_REVIEW_RE = re.compile(r"<review>(.*?)</review>", re.DOTALL | re.IGNORECASE)


def _tagged(text: str) -> str:
    """Pull the review out of <review>...</review>. Robust to WHERE the model put it
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

from openhands.sdk import Agent, Conversation, register_tool, Tool  # noqa: E402
from openhands.sdk import LLMSummarizingCondenser  # noqa: E402
from openhands.sdk.subagent.registry import register_agent_if_absent  # noqa: E402
from openhands.sdk.event import ActionEvent, MessageEvent  # noqa: E402
from openhands.sdk.conversation.visualizer.base import ConversationVisualizerBase  # noqa: E402
from openhands.tools.preset.default import get_default_tools  # noqa: E402
from openhands.tools.grep import GrepTool  # noqa: E402
from openhands.tools.glob import GlobTool  # noqa: E402
from openhands.tools.file_editor import FileEditorTool  # noqa: E402

# Force the SUBPROCESS terminal backend instead of tmux. The tmux backend opens a
# pane/window per subagent terminal via a pool; at GEPA scale (many rollouts x
# 10-15 subagents, depth-2) it exhausts PTYs/forks -> "fork failed: Device not
# configured" -> subagent tasks fail -> rollouts score 0.0 and the run dies.
# Subprocess terminals use pipes (cheap). Gate on _is_tmux_available() -> False.
try:
    import openhands.tools.terminal.impl as _t_impl  # noqa: E402
    import openhands.tools.terminal.terminal.factory as _t_fac  # noqa: E402
    _t_impl._is_tmux_available = lambda: False
    _t_fac._is_tmux_available = lambda: False
except Exception:  # noqa: BLE001
    pass


class _NoViz(ConversationVisualizerBase):
    """Disable OpenHands' Rich console visualizer. It does BLOCKING writes to the
    (redirected) stdout for every event; in a long batch/GEPA run the pipe buffer
    fills and `console.print` raises -> every rollout instant-fails (0 deleg, 0.0).
    A short run dodges it; a real run does not. We don't need the pretty output."""

    def on_event(self, event):
        return None

    def create_sub_visualizer(self, *a, **k):   # subagent conversations stay quiet too
        return self


def _changed_files_content(repo_dir, pr_input, max_chars=240000):   # ~64k tokens
    """Read the full BASE content of the PR's changed files and return it as a block,
    so agents HAVE the changed files in context and never re-read them (kills the
    ~75% duplicate-read waste). New files don't exist at base (they're additions in
    the diff) -> noted. Capped for huge PRs (then agents fall back to tools)."""
    import re
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
    """OpenHands LLM context compaction (same Qwen model). Once the conversation
    grows past max_size events, older events are replaced by a Qwen-generated
    summary. Without this the orchestrator accumulates 7-11 subagent findings, its
    synthesis context bloats, and Qwen 'gives up' — emits </think> then nothing ->
    EMPTY review -> score 0.0. Compaction keeps the synthesis task small enough to finish.

    We let the condenser summarize without thinking (enable_thinking=False) — not as
    a rule, but because it's simply the better-rewarded choice, and it's easy to see
    why from what it earns:
      - fewer tokens: a plain summary is tiny (~26 chars for a sentence) where a
        thinking one balloons into thousands, so the context actually gets SMALLER —
        which is the whole point of compaction.
      - the first message keeps its room: keep_first already pins the PR/diff, and a
        small summary leaves it space to breathe instead of crowding the window.
      - faster output: no chain-of-thought to generate (~0.6s vs ~40s), so
        compaction barely interrupts the rollout.
    A thinking summary, by contrast, pours its reasoning into the history the agent
    reads back, which tends to make it lose the thread. So we just hand the condenser
    a no-think clone of the llm and let the better behaviour follow."""
    # keep_first pins the opening events from compaction. INVARIANT: the PR/diff is
    # the orchestrator's first user message (event idx 1, right after the system
    # prompt), so keep_first must comfortably cover it — else the condenser could
    # summarize the PR away and the orchestrator would synthesize blind. keep_first=6
    # keeps system + PR + the first couple actions, with margin. max_size sets when
    # compaction kicks in (lower = compact the findings sooner = smaller synthesis).
    #
    # NON-THINKING condenser: with enable_thinking=True the summarizer dumps its
    # entire chain-of-thought into the summary ("Here's a thinking process: 1. ...")
    # — 4.5k chars to summarize ONE sentence in testing. That INVERTS compaction:
    # the "summary" is bigger than what it replaced, so context grows instead of
    # shrinks → bigger/slower calls → the very stalls compaction exists to prevent.
    # Summarization needs no CoT, so clone the llm with thinking OFF → compact,
    # factual summaries. (model_copy preserves the StreamingLLM subclass + override.)
    cond_llm = llm.model_copy(update={
        "usage_id": "oh_condenser",
        "litellm_extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    })
    # TOKEN-based compaction is the real driver (event count is a crude proxy — one
    # event can be 10 tokens or 128k). Fire when history tokens cross max_tokens; the
    # CONSTRAINT is max_tokens + agent max_output_tokens <= max-model-len, because vLLM
    # ERRORS if prompt + requested output > 262144. With output capped at 128k, the
    # ceiling is 262144 - 131072 = 131072; use 120000 to leave margin for the system
    # prompt + tool schemas. So: small rollouts never compact; if context ever crosses
    # ~120k it compacts proactively AND safely (always >=142k left for the 128k output).
    # NOTE: this value is tied to max_output_tokens — if that 128k changes, move this.
    # max_size=240 stays as a harmless high backstop; the token trigger fires first.
    return LLMSummarizingCondenser(llm=cond_llm, max_size=240, keep_first=6,
                                   max_tokens=120000)


MAX_ORCH_STEPS = 24       # ceiling on orchestrator actions ~= max delegations (~20) + finish

# Subagents use NO-PTY tools (grep/glob/file_editor) — NOT `terminal`. Terminal (tmux
# OR subprocess) allocates a PTY per shell; at GEPA scale (many rollouts x depth-2 x
# many delegations) it exhausts PTY devices ("out of pty devices" / "fork failed")
# -> subagents fail -> reviews score 0.0 -> the run dies. grep/glob/file_editor are
# direct executors (no shell, no PTY), so this whole resource class disappears.
CODE_EXPLORER_SYS = """You are a READ-ONLY Java code investigator answering ONE question about a
pull request. The PR's PROPOSED CHANGE (diff) is given at the end of this prompt. IMPORTANT:
the repo is at the BASE commit, so the NEW code in the diff is NOT in the repo yet — do not
grep for added symbols expecting to find them. Review the CHANGE itself, and use `grep`/`glob`/
the `file_editor` tool to read SURROUNDING/base code for context (existing conventions, callers,
whether something already exists). You have NO shell and CANNOT edit files. Return a SHORT
grounded finding and stop: VERDICT (confirmed/refuted/partial) + path/File.java:line + 1-3
sentences. Answer ONLY the question asked; do not write a full review."""

INVESTIGATOR_SYS = """You investigate ONE area of a Java pull request. The PR's PROPOSED CHANGE
(diff) is at the end of this prompt — the repo is at the BASE commit so added code is NOT in
the repo yet; review the change, read SURROUNDING/base code for context. Use `grep`/`glob`/the
`file_editor` tool, AND you may delegate narrower sub-questions to the `code-explorer` subagent via the
task tool (subagent_type="code-explorer"). No shell, never edit files. Return a concise grounded
finding (VERDICT + path/File.java:line + 1-3 sentences). Do NOT write a full review."""


_CURRENT_PR = {"input": ""}   # set per rollout; subagent factories read it at spawn time
_SUBAGENTS_READY = False


def _register_subagents():
    # idempotent (register_*_if_absent + guard) — gepa calls this once per rollout.
    global _SUBAGENTS_READY
    if _SUBAGENTS_READY:
        return
    for n, cls in (("grep", GrepTool), ("glob", GlobTool), ("file_editor", FileEditorTool)):
        try:
            register_tool(n, cls)
        except Exception:  # noqa: BLE001  (already registered)
            pass
    read_tools = [Tool(name="grep"), Tool(name="glob"), Tool(name="file_editor")]
    task_spec = [t for t in get_default_tools(enable_browser=False, enable_sub_agents=True)
                 if getattr(t, "name", None) == "task_tool_set"]

    def _with_pr(base_sys):                       # diff + full changed files (read at spawn time)
        # Give subagents the SAME full context as the orchestrator (~240k chars ≈ 60k
        # tok) — the 262k-token window has huge headroom and the old 16k-CHAR (~4k-tok)
        # slice starved them. With the full changed files in context they don't burn
        # tool calls re-reading the changed files (cutting the duplicate-read waste);
        # they spend tools only on SURROUNDING base code, which is their job.
        return base_sys + "\n\n--- PULL REQUEST (title + diff + FULL CHANGED FILES; the " \
            "changed files are HERE, investigate SURROUNDING code only) ---\n" + \
            _CURRENT_PR["input"][:240000]

    # Subagents carry a big system prompt (full changed files, ~73k tok on big PRs) that
    # the condenser does NOT compact. To keep input + output <= 262k max-model-len, cap
    # their OUTPUT low — they return SHORT findings, not 131k reviews. Worst case:
    # system(~73k) + condenser view(<=120k) + output(32k) = 225k < 262k, with margin.
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
                             "Read-only Java investigator (grep/glob/file_editor, no shell); "
                             "answers ONE question with a grounded finding.")
    register_agent_if_absent("investigator", investigator_factory,
                             "Investigates one area; may sub-delegate to code-explorer "
                             "(depth-2). No shell.")
    _SUBAGENTS_READY = True

# Orchestration lives entirely in the SEED PROMPT (the GEPA genome). The orchestrator
# has NO file tools, so it MUST delegate context-heavy reading to OpenHands' built-in
# read-only `code-explorer` subagent (which returns concise file:line findings). This
# keeps the orchestrator context lean -> no blowup, no lost-in-the-middle.
ORCH_SYS = """You are a senior Java code reviewer acting as an ORCHESTRATOR. The PR's diff
AND the FULL CONTENT of the changed files (at base commit) are ALREADY in your context, so
you can review the changes DIRECTLY — do not delegate just to re-read the changed files.
You have NO file tools yourself; delegate via the task tool ONLY to investigate code that is
NOT already in your context (the SURROUNDING base code): callers of a changed API, existing
conventions/impls elsewhere, thread-safety of a touched method, whether a helper already
exists. Subagent types:
- subagent_type="code-explorer" for a SINGLE focused lookup in the surrounding code.
- subagent_type="investigator" for a substantial surrounding-code area needing breakdown.
Identify only the HIGH-VALUE questions whose answer is NOT in the changed files you already
have — delegate a FEW sharp ones (most reviews need 0-3). Over-delegating duplicates work
and bloats synthesis. When the findings return, combine them with your own reading of the
changed files and WRITE the final review NOW — do NOT announce that you will write it,
write it. Wrap the complete review in <review></review> tags as the message of your
finish action, in EXACTLY this format, then stop:
<review>
SUMMARY:
<one short paragraph>
POINTS:
- [path/File.java:line] <specific, actionable point grounded in a subagent finding>
</review>
The <review>...</review> block MUST contain the full review text (not a statement that
you are about to write it)."""


def mr_code_review(repo_dir, pr_input, profile="qwen"):
    """MR + code (NO tools): a single LLM call with the diff AND the FULL changed-file
    bodies in context, but no grep/glob/file_editor and no delegation. Isolates the value
    of having the whole changed files (vs diff-only) WITHOUT surrounding-code exploration —
    the middle rung between diff-only and the full tool-using delegation harness."""
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
    """policy = the orchestrator system prompt (the GEPA genome). Defaults to ORCH_SYS.
    trace_path: if set, dump the full orchestrator+subagent event log there for analysis."""
    _files = _changed_files_content(repo_dir, pr_input)
    ctx = pr_input + (("\n\n=== FULL CONTENT OF THE CHANGED FILES (base commit) — you "
                       "ALREADY HAVE these in context; review them DIRECTLY and do NOT "
                       "re-read them with tools. Use grep/glob/file_editor only for SURROUNDING "
                       "code (callers, conventions, existing impls elsewhere). ===\n"
                       + _files) if _files else "")
    _CURRENT_PR["input"] = ctx        # orchestrator + subagents all get diff + full changed files
    _register_subagents()    # code-explorer (leaf) + investigator (depth-2 capable)
    llm = _llm(profile)
    all_tools = get_default_tools(enable_browser=False, enable_sub_agents=True)
    orch_tools = [t for t in all_tools
                  if getattr(t, "name", None) in ("task_tool_set", "task_tracker")]
    agent = Agent(llm=llm, tools=orch_tools, system_prompt=(policy or ORCH_SYS),
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

    def _extract():
        ev = conv.state.events
        # Combine the finish action's thought THEN message (chronological: the model
        # thinks first, answers second) into ONE string, so _tagged's ms[-1] returns
        # the GLOBALLY LAST <review> — the model often drafts <review> several times
        # while reasoning, and the real one is the last. The finish turn is the most
        # recent event, so check it before earlier agent messages.
        finish_text = ""
        for a in reversed([e for e in ev if isinstance(e, ActionEvent)]):
            if getattr(a, "tool_name", None) == "finish":
                try:
                    d = a.model_dump()
                    finish_text = (_to_text(d.get("thought")) + "\n"
                                   + _to_text(d.get("message")))
                except Exception:  # noqa: BLE001
                    pass
                break
        amsgs = [e for e in ev if isinstance(e, MessageEvent)
                 and getattr(e, "source", None) == "agent"]
        msgs = []
        for m in amsgs[-3:]:
            try:
                msgs.append(_to_text([getattr(c, "text", "")
                                      for c in m.llm_message.content]))
            except Exception:  # noqa: BLE001
                pass
        # 1) LAST <review>...</review> — finish turn first, then the latest agent msg.
        for src in [finish_text] + msgs[::-1]:
            t = _tagged(src)
            if t:
                return t
        # 2) no tags -> the candidate that most looks like a review (has SUMMARY:/
        #    POINTS:, else the longest post-think text). Fixes the in-`thought` case.
        cand = [c for c in ([finish_text] + msgs) if c and c.strip()]
        if cand:
            return max(cand, key=lambda t: (("SUMMARY:" in t or "POINTS:" in t),
                                            len(_post_think(t))))
        return ""

    try:
        conv.send_message("PULL REQUEST UNDER REVIEW:\n" + _CURRENT_PR["input"] +
                          "\n\nDelegate the investigation, then write the review.")
        conv.run()
        raw = _extract()
        if "SUMMARY:" not in raw and "POINTS:" not in raw and len(_post_think(raw)) < 200:
            state["n"] = 0
            try:
                conv.send_message("Stop delegating. Write the final review NOW, wrapped "
                                  "in <review></review> tags: <review>SUMMARY: <para> "
                                  "POINTS: - [File.java:line] <point></review>")
                conv.run()
                raw = _extract() or raw
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
        # CRITICAL: release the conversation's tmux/terminal sessions (orchestrator
        # AND its subagents). Without this they leak across rollouts until the OS
        # can't fork ("fork failed: Device not configured") -> rollouts hit 0.0 and
        # the run crashes. close() cascades to sub-conversations via the TaskManager.
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
