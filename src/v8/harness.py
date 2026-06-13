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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ on path
from v8.llm import _llm, _to_text, _post_think  # noqa: E402  reuse
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
from v8 import search_tool  # noqa: E402,F401  registers the "search" tool (ripgrep + context)

# v2 toolset switch: when OH_SEARCH_V2 is set, subagents also get `search` (content+context,
# single-file) and are told to prefer it over grep->view. Gated so the baseline stays pure.
_V2 = bool(os.environ.get("OH_SEARCH_V2"))
_SEARCH_GUIDE = (
    "\n\nPREFER the `search` tool to READ code: search(pattern, path=<file_or_dir>, "
    "context=N) returns the matching lines WITH surrounding context (file:line: code) in "
    "ONE call — use it to read a method body, a config block, or a symbol's "
    "definition/usages. It accepts a single FILE and repo-relative paths. Use `grep`/`glob` "
    "only to LOCATE files, and `file_editor view` only when you need a large contiguous "
    "region you can't target by pattern. Don't grep for a filename then view the whole "
    "file — one `search` does it.")

# v4 = search + verify-impact (kept from v3) + BREADTH-preserving language (replaces
# v3's wrap-up-early, which suppressed survey findings: v3 goods 3.06/PR vs v2 3.82) +
# path normalization + PR-added-file manifest. Same calm register throughout.
_V4 = bool(os.environ.get("OH_V4"))
_V5 = bool(os.environ.get("OH_V5"))
_V6 = bool(os.environ.get("OH_V6"))
_V7 = bool(os.environ.get("OH_V7"))
_V9 = bool(os.environ.get("OH_V9"))   # v9: relaxed orchestrator (no artificial limits on investigation)
if _V9:
    _V7 = True              # v9 builds on v7's lean context + tools
if _V7:
    _V6 = True              # v7 includes the v6 PR tools
if _V6:
    _V5 = True              # v6 includes everything v5 has
if _V5:
    _V4 = True              # v5 includes everything v4 has

# v7: lean subagent context. Subagents keep the full diff (with the complete changed-file
# list in the header) but no longer carry the 240k changed-files block — the base content
# of any file is one file_editor/search call away, and the pr tools cover the PR side.
# This frees ~64k tokens of every subagent call for investigation view + output.
_V7_SUB_GUIDE = (
    "\n\nYour context carries the pull request's diff and the complete list of files it "
    "changes; the repository at the base commit is on disk. When you need the base "
    "content of a changed file, read it with file_editor or search — it is not in this "
    "prompt. The diff above is the change itself; the tools give you everything around it.")
if _V4:
    from v8 import path_norm
    path_norm.install()
    _V2 = True              # v4 includes the search tool wiring

# v6: the PR as a queryable object — `pr_files` (complete changed-file list) and
# `pr_file_diff` (the complete diff of one file from git). Closes the last truncation
# gap: even v5's 150k inline diff is cut on the biggest PRs, and subagents otherwise
# have no way to see past the cut.
_V6_SUB_GUIDE = (
    "\n\nTwo further tools describe the pull request itself: `pr_files` lists every "
    "file the PR changes (status and line counts), and `pr_file_diff` returns the "
    "complete diff the PR makes to one file, straight from git — including anything "
    "cut from the diff text above. When the inline diff is marked truncated, or you "
    "need certainty about what the PR does to a specific file, ask git rather than "
    "infer: what `pr_file_diff` returns is the whole change to that file.")

# v5 fixes #2 + #4 (subagent side), derived from Claude-judge fabrication tracing:
# asymmetric verification (a base-repo check can never prove the PR lacks something)
# and the findings ledger (66% of misses were topics touched in dialog but never
# surfaced as findings). Calm register, as always.
_V5_SUB_GUIDE = (
    "\n\nTwo habits from reviewing past investigations. First, absence works differently "
    "from presence: the repo here is the BASE commit, so not finding something in it can "
    "never show that the pull request lacks it — the change may simply sit beyond what "
    "you can see. Report what you positively observed in the visible diff or code; if "
    "you suspect something is missing but cannot see the whole change, say so as an open "
    "question rather than a finding. Second, keep a small ledger as you read: any "
    "candidate issue you notice along the way — even minor or uncertain — belongs in "
    "your report with a one-line note and your confidence. The reviewer assembling the "
    "final review can only use what you hand over; an observation kept in your head is "
    "a finding lost.")

# v5 fix #3 (orchestrator side): hedge preservation through synthesis — a subagent's
# "the PR must be adding this" must not become "missing X" in the review.
_V5_ORCH_GUIDE = (
    "\n\nWhen you assemble the final review from the findings, keep each claim at the "
    "confidence its evidence supports. A finding hedged as 'probably' or 'the PR must "
    "be adding this' stays hedged or becomes a question to the author — promoting it to "
    "a definite 'missing'/'broken' claim is how fabrications are born, and one fabricated "
    "blocker costs more credibility than three good findings earn. Walk through every "
    "observation your investigators handed you and either include it, fold it into "
    "another point, or consciously drop it — unexamined observations are missed findings. "
    "The repo is at the base commit: nobody can prove the PR lacks something by its "
    "absence from the base tree or from a truncated diff.")


def _added_files_manifest(pr_input):
    """W-fix #2: list files ADDED by the PR (32% of subagent sessions burn ~5 turns
    hunting these on disk before concluding they only exist in the diff)."""
    added = re.findall(r"^--- /dev/null\n\+\+\+ b/(\S+)", pr_input or "", re.MULTILINE)
    if not added:
        added = re.findall(r"^diff --git a/(\S+) b/\S+\nnew file", pr_input or "", re.MULTILINE)
    if not added:
        return ""
    return ("\n\nNote: these files are ADDED by this PR and are NOT on disk at the base "
            "commit — read their content from the diff below rather than searching the "
            "repo for them: " + ", ".join(sorted(set(added))[:30]))
_FOCUS_GUIDE_V4 = (
    "\n\nTwo habits make an investigation most useful. First, confirm impact: for a "
    "changed or removed symbol, a quick look at who calls or imports it shows what the "
    "change really affects — that is what turns an observation into an actionable "
    "finding. Second, keep your eyes open along the way: adjacent issues you notice "
    "while reading are worth including — give each the same quick check against the "
    "code (the file and line that shows it) before adding it, since one confirmed "
    "finding outweighs several guesses. A finding list that covers the whole change, "
    "with each point verified, is the most valuable report you can return.")

# W3 focus guidance: a calm, reward-framed nudge toward a focused investigation that
# verifies impact and then wraps up. Deliberately NOT written as caps/"STOP"/"MUST" —
# the subagent's register propagates into its finding and then into the final review's
# tone of voice, so the guidance reads as normal professional advice.
_FOCUS = bool(os.environ.get("OH_FOCUS"))
_FOCUS_GUIDE = (
    "\n\nA focused investigation is the most useful kind. Once you've answered the "
    "specific question, it helps to confirm what it means in practice — for a changed or "
    "removed symbol, a quick look at who calls or imports it shows the real impact, and "
    "that is what turns an observation into an actionable finding. After that the finding "
    "is complete: tracing the wider call graph or unrelated code usually adds length "
    "without changing the conclusion, so it's natural to wrap up and report what you "
    "found. Aim for the smallest investigation that fully answers the question and "
    "confirms its impact.")

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

# v9: relaxed investigator. The soft "may delegate" becomes a real trigger, and the
# "concise / 1-3 sentences" limiter is dropped so a multi-instance area is covered in full.
INVESTIGATOR_SYS_V9 = """You investigate ONE area of a Java pull request. The PR's PROPOSED CHANGE
(diff) is at the end of this prompt — the repo is at the BASE commit so added code is NOT in the
repo yet; review the change and read SURROUNDING/base code for context with `grep`/`glob`/`file_editor`.
When your area has MULTIPLE instances to check — several overloads, call-sites, branches, or files —
or a sub-question needs its own focused lookup, delegate it to the `code-explorer` subagent via the
task tool (subagent_type="code-explorer") and check ALL instances rather than generalizing from one.
Cover every instance in your assignment, then CONCLUDE and return — use a focused set of lookups
(and code-explorer only for genuinely separate sub-questions), not an open-ended exploration; once
you have checked the instances you were asked about, stop and report. Do not re-open areas you have
already checked or widen beyond your assigned area. No shell, never edit files. Return a grounded
finding: VERDICT + path/File.java:line + the specific evidence, covering every instance you were
asked about. Do NOT write a full review."""


_CURRENT_PR = {"input": ""}   # set per rollout; subagent factories read it at spawn time
_SUBAGENTS_READY = False


def _register_subagents():
    # idempotent (register_*_if_absent + guard) — gepa calls this once per rollout.
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
    read_tools = [Tool(name="grep"), Tool(name="glob"), Tool(name="file_editor")]
    if _V2:
        read_tools = [Tool(name="search")] + read_tools     # search first = preferred
    if _V6:
        read_tools = read_tools + [Tool(name="pr_files"), Tool(name="pr_file_diff")]
    task_spec = [t for t in get_default_tools(enable_browser=False, enable_sub_agents=True)
                 if getattr(t, "name", None) == "task_tool_set"]

    def _with_pr(base_sys):                       # diff + full changed files (read at spawn time)
        # Give subagents the SAME full context as the orchestrator (~240k chars ≈ 60k
        # tok) — the 262k-token window has huge headroom and the old 16k-CHAR (~4k-tok)
        # slice starved them. With the full changed files in context they don't burn
        # tool calls re-reading the changed files (cutting the duplicate-read waste);
        # they spend tools only on SURROUNDING base code, which is their job.
        # v4 (user decision after two failed breadth smokes) = v3's proven guidance +
        # path normalization ONLY. _FOCUS_GUIDE_V4 and the manifest stay unused.
        # v5 adds the asymmetric-verification + findings-ledger guidance on top.
        guide = (_SEARCH_GUIDE if _V2 else "") + \
            (_FOCUS_GUIDE if (_FOCUS or _V4) else "") + \
            (_V5_SUB_GUIDE if _V5 else "") + \
            (_V6_SUB_GUIDE if _V6 else "") + \
            (_V7_SUB_GUIDE if _V7 else "")
        if _V7:   # lean context: diff + complete file list only; base content via tools
            return base_sys + guide + "\n\n--- PULL REQUEST (title + complete changed-file " \
                "list + diff; base content of any file is on disk — read it with tools) ---\n" + \
                (_CURRENT_PR.get("sub") or _CURRENT_PR["input"])[:240000]
        return base_sys + guide + "\n\n--- PULL REQUEST (title + diff + FULL CHANGED FILES; the " \
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
        return Agent(llm=sl, tools=read_tools + task_spec,
                     system_prompt=_with_pr(INVESTIGATOR_SYS_V9 if _V9 else INVESTIGATOR_SYS),
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

# v9: relaxed orchestrator. Removes the anchors that caused v8's depth misses — the
# "0-3 delegations / over-delegating bloats", the "review changed files directly, don't
# delegate them", and the "write the review now" early-stop. Investigation scales to the
# PR; changed-file correctness (esp. multi-instance checks) is delegable; verify before
# asserting absence/criticality. Only the hard physical bounds remain (vLLM ceiling, the
# MAX_ORCH_STEPS backstop). The output format is unchanged.
ORCH_SYS_V9 = """You are a senior Java code reviewer acting as an ORCHESTRATOR. The PR's diff
AND the FULL CONTENT of the changed files (at base commit) are ALREADY in your context. You have
NO file tools yourself; you investigate by delegating via the task tool to subagents that read the repo.

Your goal is the most thorough, correct review this PR warrants — find every substantive,
non-obvious issue a strong reviewer would raise, and VERIFY each against the actual code before
asserting it. There is no fixed budget on the number of investigations: investigate as much as the
PR needs. A large or subtle PR may warrant many delegations; a small one only a few. Scale your
effort to the PR — do not stop early to save calls, and do not pad a simple PR.

Delegate to check anything you cannot verify from your own context alone, including:
- CHANGED-FILE correctness: when a changed method/class has multiple overloads, branches, call-sites,
  or sibling files, delegate a check across ALL of them (e.g. "verify every getX overload escapes its
  input", "find all callers of the changed signature and confirm they pass the new argument") rather
  than generalizing from a single example;
- SURROUNDING/base code: callers, existing conventions, whether a helper already exists, thread-safety,
  prior behavior.
Before you assert that something is missing, broken, untested, or critical, delegate a check that
confirms it against the code — unconfirmed absence/criticality claims are the main error to avoid.

Subagent types:
- subagent_type="investigator" for a substantial area that may need several lookups or its own sub-delegation.
- subagent_type="code-explorer" for a single focused lookup.

Keep investigating until the substantial claims are verified and nothing material is left to check.
Then combine the findings with your own reading and write the COMPLETE review — do not announce it,
write it. Wrap it in <review></review> tags as the message of your finish action, in EXACTLY this
format, then stop:
<review>
SUMMARY:
<one short paragraph>
POINTS:
- [path/File.java:line] <specific, actionable, verified point>
</review>
The <review>...</review> block MUST contain the full review text (not a statement that you are
about to write it)."""


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
    _CURRENT_PR["sub"] = pr_input if _V7 else None   # v7: subagents get the diff only
    _register_subagents()    # code-explorer (leaf) + investigator (depth-2 capable)
    llm = _llm(profile)
    all_tools = get_default_tools(enable_browser=False, enable_sub_agents=True)
    orch_tools = [t for t in all_tools
                  if getattr(t, "name", None) in ("task_tool_set", "task_tracker")]
    _base_orch = ORCH_SYS_V9 if _V9 else ORCH_SYS
    orch_sys = (policy or _base_orch) + (_V5_ORCH_GUIDE if _V5 else "")
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
                    msg = d.get("message")
                    if msg is None:          # finish tool nests its message under "action"
                        msg = (d.get("action") or {}).get("message")
                    finish_text = (_to_text(d.get("thought")) + "\n"
                                   + _to_text(msg))
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
