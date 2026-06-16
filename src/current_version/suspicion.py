"""Suspicion-driven review — the fact-checked worklist architecture.

A shared SUSPICION LIST is grown and fact-checked until it runs dry:
  generate   -> raise candidate issues (hypotheses) from the diff       [agent, read tools]
  schedule   -> pull the most promising PENDING suspicion               [agent]
  fact-check -> confirm/refute/partial against the REAL code, and        [agent, read tools]
                add any new suspicions noticed while reading
  synthesize -> review = confirmed suspicions (+ partials as questions)  [agent]

Budget is on the LIST, not the agents: fact-check every suspicion whose
severity x confidence clears a quality FLOOR; stop when nothing pending clears it (run dry),
with a high backstop on total checks. Fact-checking is the falsification step — a suspicion
is never a finding until confirmed, so confident-but-wrong claims (fabrications) are refuted
and dropped by construction.

  ./venv-oh/bin/python -u src/v8/suspicion.py quarkusio/quarkus 6913
"""
from __future__ import annotations
import json, os, re, sys, warnings
from dataclasses import dataclass, asdict

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ on path
from current_version import harness                                   # reuse _llm/_condenser/_NoViz/_changed_files_content
from current_version.llm import _to_text, _post_think                 # noqa: E402
from openhands.sdk import Agent, Conversation, Tool       # noqa: E402
from openhands.sdk.event import ActionEvent, MessageEvent  # noqa: E402
from openhands.sdk.tool import (Action, DeclaredResources, Observation, ToolAnnotations,  # noqa: E402
                                ToolDefinition, ToolExecutor, register_tool as _register_tool)
from pydantic import Field                                 # noqa: E402
from collections.abc import Sequence                       # noqa: E402
from llm_client import get_llm, final_review              # noqa: E402


# --- the suspicion store + add_suspicion tool -------------------------------------------
# A persistent, process-owned list. Agents WRITE each suspicion via the tool the moment they
# notice it, so it survives the agent's context compaction and any output-parse failure
# (the JSON-array-at-the-end approach lost suspicions on both). The loop owns it; reset per PR.

_STORE = []   # list of dicts {id, claim, location, severity, confidence}


def _reset_store():
    _STORE.clear()


def _store_add(observation, suspected_bug, location, severity, confidence):
    sid = len(_STORE)
    _STORE.append({"id": sid, "observation": str(observation), "suspected_bug": str(suspected_bug),
                   "location": str(location), "severity": str(severity).lower(), "confidence": confidence})
    return sid


_VERDICT = {}   # the reproducer writes its verdict here via the record_verdict tool (not parsed prose)


def _reset_verdict():
    _VERDICT.clear()


_FIX = {}   # the solver writes its fix here via the record_fix tool


def _reset_fix():
    _FIX.clear()


class AddSuspicionAction(Action):
    observation: str = Field(description="What you LITERALLY SEE in the code that looks off — the concrete "
                             "factual thing (a specific line, name, call, value). Not a judgment; you must "
                             "have actually seen it.")
    suspected_bug: str = Field(description="The bug you SUSPECT this causes — the hypothesized problem, one "
                               "line. A guess for the reproducer to reproduce or drop; you need not be sure.")
    location: str = Field(description="File.java:line or area where the observation is.")
    severity: str = Field(description="critical | high | medium | low (impact IF the bug is real).")
    confidence: float = Field(description="0-1, your prior that it is a real bug, pre-reproduction.")


class AddSuspicionObservation(Observation):
    pass


_ADD_DESC = ("Record ONE suspicion — an OBSERVATION (something you literally saw that looks off) plus the "
             "suspected_bug it might cause. A candidate for the REPRODUCER to reproduce later, NOT a confirmed "
             "finding. Raise it the MOMENT something looks off; do not verify it yourself. Skip pure chores "
             "('verify X') and pure speculation ('might be slow'). Call once per suspicion. "
             "Args: observation, suspected_bug, location, severity (critical/high/medium/low), confidence (0-1).")


class _AddSuspicionExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        sid = _store_add(action.observation, action.suspected_bug, action.location,
                         action.severity, action.confidence)
        return AddSuspicionObservation.from_text(text=f"recorded suspicion #{sid}: {str(action.suspected_bug)[:60]}")


class AddSuspicionTool(ToolDefinition[AddSuspicionAction, AddSuspicionObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[AddSuspicionTool]":  # noqa: ARG003
        return [cls(description=_ADD_DESC, action_type=AddSuspicionAction,
                    observation_type=AddSuspicionObservation,
                    annotations=ToolAnnotations(title="add_suspicion", readOnlyHint=False,
                                                destructiveHint=False, idempotentHint=False,
                                                openWorldHint=False),
                    executor=_AddSuspicionExecutor())]


# --- record_verdict: the reproducer's decision is CAPTURED BY A TOOL, not parsed from prose ---
# The loop used to regex the final message for {"verdict":...}; when the model wrote its decision in
# prose ("the logger issue — confirmed, uses ReflectiveHierarchyStep.class") the parse failed and the
# verdict SILENTLY defaulted to "partial", losing real confirms. A tool call is robust to verbosity.
class RecordVerdictAction(Action):
    verdict: str = Field(description="confirmed | refuted. confirmed ONLY if you REPRODUCED the bug by "
                         "RUNNING code — a test that FAILED/won't compile, or output/logs showing the wrong "
                         "behavior. If the run was clean, or you could not reproduce it, the verdict is "
                         "refuted. (partial only for a genuinely-substantive bug no runnable repro could settle.)")
    repro_kind: str = Field(description="test | log | none. test = you wrote & RAN a unit test/driver that "
                            "FAILED (or failed to compile). log = you added logging/print, RAN it, and the "
                            "output shows the wrong behavior. none = you did not run a reproduction.")
    reproduction: str = Field(description="The actual RUN: the command(s) you executed in sandbox_exec and "
                       "their real output — the failing assertion, the compile error, or the log line showing "
                       "the wrong value. This must SHOW the bug happening, not assert it from reading.")
    evidence: str = Field(description="One-line summary: file:line + the concrete bug (or why not reproduced).")


class RecordVerdictObservation(Observation):
    pass


_VERDICT_DESC = ("Record your decision on the one suspicion, ONCE, LAST. You are a REPRODUCER, not a judge: "
                 "verdict=confirmed REQUIRES that you REPRODUCED the bug by RUNNING code — `test` (a unit "
                 "test/driver you wrote and ran that FAILED or won't compile) or `log` (logging/print you "
                 "added, ran, whose output shows the wrong behavior). Reading the code is NOT reproduction. "
                 "If the run is clean, or you could not build a runnable repro, record refuted (repro_kind="
                 "none). Do not confirm a plausibility. "
                 "Args: verdict, repro_kind (test/log/none), reproduction (the command(s) run + real output), evidence.")


class _RecordVerdictExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _VERDICT["verdict"] = str(action.verdict).lower().strip()
        _VERDICT["repro_kind"] = str(action.repro_kind).lower().strip()
        _VERDICT["reproduction"] = str(action.reproduction)
        _VERDICT["evidence"] = str(action.evidence)
        # guard: a 'confirmed' with no executed reproduction is the failure mode we are killing — downgrade it.
        if _VERDICT["verdict"] == "confirmed" and _VERDICT["repro_kind"] not in ("test", "log"):
            _VERDICT["verdict"] = "refuted"
            return RecordVerdictObservation.from_text(
                text="confirmed REQUIRES repro_kind=test|log with a real RUN; none given -> recorded refuted")
        return RecordVerdictObservation.from_text(text=f"recorded verdict: {_VERDICT['verdict']} ({_VERDICT['repro_kind']})")


class RecordVerdictTool(ToolDefinition[RecordVerdictAction, RecordVerdictObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[RecordVerdictTool]":  # noqa: ARG003
        return [cls(description=_VERDICT_DESC, action_type=RecordVerdictAction,
                    observation_type=RecordVerdictObservation,
                    annotations=ToolAnnotations(title="record_verdict", readOnlyHint=False,
                                                destructiveHint=False, idempotentHint=False,
                                                openWorldHint=False),
                    executor=_RecordVerdictExecutor())]


# --- record_fix: the SOLVER records its fix (the patch + the verified rerun) -----------------
class RecordFixAction(Action):
    fixed: bool = Field(description="true if your change makes the reproduced value come out right on "
                        "/src/new with nothing else broken; false if you could not fix it.")
    fix_diff: str = Field(default="", description="the change you made to the real lines, as a diff (the "
                          "logic fix only — not the reproduction's logging).")
    rerun: str = Field(default="", description="the rerun output showing the value now correct on /src/new "
                       "and the other findings / module tests still passing.")


class RecordFixObservation(Observation):
    pass


_FIX_DESC = ("Record your fix for the one bug, once, last. fixed=true only if re-running the reproduction "
             "against your changed code shows the value now correct on /src/new and nothing else broken. "
             "Give the fix_diff (the logic change to the real lines) and the rerun output. Smaller fixes "
             "score higher. If you couldn't fix it, fixed=false.")


class _RecordFixExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _FIX["fixed"] = bool(action.fixed)
        _FIX["fix_diff"] = str(action.fix_diff)
        _FIX["rerun"] = str(action.rerun)
        return RecordFixObservation.from_text(text=f"recorded fix: fixed={_FIX['fixed']}")


class RecordFixTool(ToolDefinition[RecordFixAction, RecordFixObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[RecordFixTool]":  # noqa: ARG003
        return [cls(description=_FIX_DESC, action_type=RecordFixAction,
                    observation_type=RecordFixObservation,
                    annotations=ToolAnnotations(title="record_fix", readOnlyHint=False,
                                                destructiveHint=False, idempotentHint=False,
                                                openWorldHint=False),
                    executor=_RecordFixExecutor())]


# --- the sandbox_exec tool: PROVE a suspicion by execution (contract P17) ----------------
# Runs arbitrary bash in the per-session Java container on the remote Docker host (server2).
# The fact-checker writes a snippet/test, compiles, runs it — the compiler/runtime settles
# binding/signature/contract/runtime claims that text reading only guesses at. Sandboxed: it
# writes only inside the container, never the host or the repo checkout.
from current_version import sandbox as _sandbox   # noqa: E402


class SandboxExecAction(Action):
    command: str = Field(description="bash to run INSIDE the Java sandbox container. Write a "
                         "file with a heredoc, compile with javac, run with java (or mvn). "
                         "Returns combined stdout+stderr and the exit code.")
    version: str = Field(default="new", description="which checked-out tree to run in (cwd): "
                         "'new' = the POST-PR code at /src/new (default — what you are "
                         "reviewing), 'old' = the base code at /src/old. Both are full source "
                         "trees; cd into subdirs, javac/grep/cat real files of that version.")


class SandboxExecObservation(Observation):
    pass


_SBX_DESC = ("Run bash in a Java sandbox container to PROVE a claim by EXECUTION. BOTH source trees are "
             "mounted as normal checkouts: /src/new (post-PR, cwd via version='new') and /src/old (base). "
             "Work in /src/new like a developer: write a tiny test/snippet next to the code, `javac` it "
             "(classpath the real tree if needed), `java` it — the compiler resolves overloads/signatures/"
             "types exactly and the runtime shows whether it actually throws/misbehaves. version='old' runs "
             "against the base tree (before/after comparison). You may freely create/edit/compile files: the "
             "tree is git-reset to pristine before the next suspicion, and you can reset it yourself anytime "
             "with `reset_workspace` (e.g. to get a clean baseline).")


class _SandboxExecExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        rc, out = _sandbox.exec_(action.command, version=getattr(action, "version", "new"))
        return SandboxExecObservation.from_text(text=f"exit={rc}\n{out}")


class SandboxExecTool(ToolDefinition[SandboxExecAction, SandboxExecObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[SandboxExecTool]":  # noqa: ARG003
        return [cls(description=_SBX_DESC, action_type=SandboxExecAction,
                    observation_type=SandboxExecObservation,
                    annotations=ToolAnnotations(title="sandbox_exec", readOnlyHint=False,
                                                destructiveHint=False, idempotentHint=False,
                                                openWorldHint=True),
                    executor=_SandboxExecExecutor())]


# --- reset_workspace: the prover resets the source trees to pristine itself ----------------
# Work in /src/new like a normal checkout; when you want a clean slate (you edited a file to test
# something, or you want a clean before/after baseline), call this — git checkout+clean both trees.
class ResetWorkspaceAction(Action):
    pass


class ResetWorkspaceObservation(Observation):
    pass


_RESET_DESC = ("Reset BOTH source trees (/src/new and /src/old) to pristine HEAD — discards every edit, "
               "stray file, and build artifact you made. Call it to get a clean slate: after an experiment "
               "that modified files, or before a clean before/after comparison. You may write/compile/run "
               "freely in /src/new; this (and the automatic reset before the next suspicion) cleans it up.")


class _ResetWorkspaceExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _sandbox.reset_clean()
        return ResetWorkspaceObservation.from_text(text="workspace reset: /src/new and /src/old are pristine HEAD")


class ResetWorkspaceTool(ToolDefinition[ResetWorkspaceAction, ResetWorkspaceObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[ResetWorkspaceTool]":  # noqa: ARG003
        return [cls(description=_RESET_DESC, action_type=ResetWorkspaceAction,
                    observation_type=ResetWorkspaceObservation,
                    annotations=ToolAnnotations(title="reset_workspace", readOnlyHint=False,
                                                destructiveHint=False, idempotentHint=True,
                                                openWorldHint=False),
                    executor=_ResetWorkspaceExecutor())]


# --- prompts (the genome for this architecture) -----------------------------------------

SUSPECTOR_SYS = """You're reading through a pull request looking for anything that might be a bug — any
place the change could be wrong. Lean generous: a suspicion costs nothing, since another agent reproduces
each one and throws out the wrong ones, but a bug you don't flag is gone for good — so when in doubt, flag
it, and err toward more. What's worth flagging is something specific in the change (a line, name, call, or
value that looks off) and the bug it might cause.

Don't weigh whether each one really holds up — that's the reproducer's job, not yours — and don't keep them
in your head, since a long read loses them: the moment something catches your eye, jot it down with
add_suspicion and keep going. Work all the way through the diff, every changed file, flagging as you go, so
nothing slips past. For each: what you saw (observation), the bug you suspect (suspected_bug), where it is
(location), how serious it would be if real (severity), and how sure you are (confidence)."""

SCHEDULER_SYS = """You pick which pending suspicion the reproducer should try next — the one most worth
settling now, a serious suspected bug that's plausible but not yet reproduced. Return ONLY {"id": N}."""

REPRODUCER_SYS = """You're given one suspected bug in a Java project — an observation and the problem it
might cause, at a location. The question is whether it's real, and the way to settle it is to get the real
code to show it. You can add logging into the real source to watch what it does, and write whatever
throwaway drivers help; the code's behaviour stays as the project wrote it — you're watching it, not
changing it. You have the project at two versions you can build and run, /src/new (with the change) and
/src/old (without), and a sandbox.

What the run earns, read from what the real code actually prints:
  - the genuine project code runs — the real classes, not a copy or a sketch of them;
  - a log you added inside the real source prints while it runs;
  - that printed value comes out wrong on /src/new but right on /src/old — the bug showing itself in
    this change.

If you can't get the real code to misbehave, that's a fine answer too — the bug is probably not there, and
nothing about a copy you've altered yourself would count, since the reward is only about how the real code
behaves.

How you get there is up to you — add logging to the real files, write throwaway drivers, reset the
workspace whenever you like (it's cleaned between bugs). Compile the real module with `javac -cp <deps>`
rather than fighting Maven. When you've done your best, record what you found with record_verdict: whether
it's real, and the run plus its output on both versions that shows it.

You're down in the real code now — closer to it than the suspector who handed this to you. Often the
actual problem sits a little to the side of what you were given, or there's a separate bug nearby that
catches your eye. When that happens, raise it with add_suspicion (observation + suspected_bug) — it gets
its own look, with its own reproduction and fix. A sharper suspicion you raise is worth as much as the
one you were asked to settle, so don't let it pass."""

SOLVER_SYS = """You're handed a bug that's already been shown to be real — in the real code's own logging
you can see a value coming out wrong on /src/new and right on /src/old, with the driver that triggers it.
Your task is to fix it: change the real code so the problem is gone.

What the fix earns, checked by re-running that same reproduction against your changed code:
  - with your fix in, that value now comes out right on /src/new;
  - nothing else breaks — the other findings and the module's tests stay green;
  - the smaller the change, the better — a tight fix at the root cause beats a sprawling one (the score
    scales with 1 / lines changed).

You can change anything in the source to get there. The reproduction's driver and logging that grade you
stay as they are — you don't need to touch them and editing them doesn't help. Work in /src/new with the
sandbox; reset_workspace whenever you like. When you've done your best, record it with record_fix: the
change you made (a diff of the real lines) and the rerun showing the value now right and everything still
passing. If you genuinely can't fix it, that's a fine outcome — leave it for the author."""

SYNTHESIZER_SYS = """You write the final Java code review from CONFIRMED findings only — each one a bug the
reproducer showed in the real code, some with a fix the solver verified. Turn each into a point with its
file:line, what the bug is, and the fix if there is one. Add no new claims of your own. A short, sharp
review beats a flood. Output SUMMARY: then POINTS:, each as - [path/File.java:line] <bug> [— fix: <fix>]."""


SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class Suspicion:
    id: int
    observation: str                  # what the suspector literally saw
    suspected_bug: str                # the bug it might cause (hypothesis)
    location: str
    severity: str
    confidence: float
    status: str = "pending"           # pending / confirmed / refuted / partial
    evidence: str = ""
    repro_kind: str = ""              # test / log / none — how the bug was reproduced by EXECUTION
    reproduction: str = ""            # the actual run: command(s) + their output manifesting the bug
    fixed: bool = False               # solver verified a fix (only attempted on confirmed bugs)
    fix_diff: str = ""                # the logic change the solver made to the real lines
    fix_rerun: str = ""               # the rerun output proving the fix + nothing else broken

    def value(self) -> float:
        try:
            return SEV.get(str(self.severity).lower(), 1) * float(self.confidence)
        except Exception:  # noqa: BLE001
            return 1.0


def _extract_json(text, opener):
    """Return the LAST balanced JSON value starting with opener ('[' or '{'), or None."""
    close = "]" if opener == "[" else "}"
    for s in reversed([i for i, c in enumerate(text) if c == opener]):
        depth = 0
        for j in range(s, len(text)):
            if text[j] == opener:
                depth += 1
            elif text[j] == close:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[s:j + 1])
                    except Exception:  # noqa: BLE001
                        break
    return None


def _final_text(events):
    """Final assistant text of a finished conversation (finish-action message, then last msg)."""
    for a in reversed([e for e in events if isinstance(e, ActionEvent)]):
        if getattr(a, "tool_name", None) == "finish":
            d = a.model_dump()
            msg = d.get("message") or (d.get("action") or {}).get("message")
            t = _to_text(d.get("thought")) + "\n" + _to_text(msg)
            if t.strip():
                return t
            break
    amsgs = [e for e in events if isinstance(e, MessageEvent) and getattr(e, "source", None) == "agent"]
    for m in reversed(amsgs[-3:]):
        try:
            t = _to_text([getattr(c, "text", "") for c in m.llm_message.content])
            if t.strip():
                return t
        except Exception:  # noqa: BLE001
            pass
    return ""


_TOOLS_READY = False


def _read_tools():
    global _TOOLS_READY
    if not _TOOLS_READY:
        harness._register_subagents()    # registers search/grep/glob/file_editor/pr_files/pr_file_diff
        for _n, _t in (("add_suspicion", AddSuspicionTool), ("sandbox_exec", SandboxExecTool),
                       ("record_verdict", RecordVerdictTool), ("reset_workspace", ResetWorkspaceTool),
                       ("record_fix", RecordFixTool)):
            try:
                _register_tool(_n, _t)
            except Exception:  # noqa: BLE001  (already registered)
                pass
        _TOOLS_READY = True
    return [Tool(name=n) for n in ("search", "grep", "glob", "file_editor", "pr_files", "pr_file_diff")]


CAPTURE = "add_suspicion"


def _run_agent(system_prompt, user_msg, repo_dir, extra_tools=(), version="new"):
    """Run a tool-using agent to completion; return its final (post-think) text. The read
    tools (search/grep/glob/file_editor) are rooted at the agent's workspace, which we point
    at the POST-PR tree by default (version='new') so added/renamed files are on disk and
    searchable — base-only was the dominant cause of under-confirming. `version='old'` (or no
    live sandbox session) falls back to the base checkout."""
    ws = _sandbox.workdir(version) or str(repo_dir)
    tools = _read_tools() + [Tool(name=n) for n in extra_tools]
    # PER-TURN output cap = 32768 (NOT a limit on the review — a turn emits a verdict + a few tool
    # calls). The base 131072 reserves half the 262144 window for output, leaving only ~11k tokens
    # of condenser margin (120000 + 131072 = 251072) — one big tool read overshoots → vLLM 400 (the
    # 6222 crash). 32768 gives the prompt a ~109k-token margin and satisfies the P14 invariant.
    llm = harness._llm("qwen").model_copy(update={"usage_id": "oh_suspicion", "max_output_tokens": 32768})
    agent = Agent(llm=llm, tools=tools, system_prompt=system_prompt, condenser=harness._condenser(llm))
    conv = Conversation(agent=agent, workspace=ws, visualizer=harness._NoViz, persistence_dir=None)
    try:
        conv.send_message(user_msg)
        conv.run()
        return _post_think(_final_text(conv.state.events))
    finally:
        try:
            conv.close()
        except Exception:  # noqa: BLE001
            pass


def _llm_call(system_prompt, user_msg, profile="qwen"):
    return _post_think(get_llm(profile).complete(system_prompt, user_msg, temperature=0.0))


# --- the four roles ---------------------------------------------------------------------

def _store_to_suspicions(by_id):
    """Pull any store entries not yet tracked into by_id as pending Suspicion objects."""
    for d in _STORE:
        if d["id"] not in by_id:
            try:
                by_id[d["id"]] = Suspicion(id=d["id"], observation=d["observation"],
                                           suspected_bug=d["suspected_bug"], location=d["location"],
                                           severity=d["severity"], confidence=float(d["confidence"]))
            except Exception:  # noqa: BLE001
                pass


def generate(repo_dir, ctx):
    _run_agent(SUSPECTOR_SYS, "PULL REQUEST:\n" + ctx +
               "\n\nRecord the suspicions now — call add_suspicion once for each (observation + suspected_bug).",
               repo_dir, extra_tools=[CAPTURE])
    by_id = {}
    _store_to_suspicions(by_id)
    return by_id


def schedule(pending):
    lst = "\n".join(f"[{s.id}] sev={s.severity} conf={s.confidence} :: {s.suspected_bug} ({s.location})"
                    for s in pending)
    try:
        obj = _extract_json(_llm_call(SCHEDULER_SYS, "PENDING SUSPICIONS:\n" + lst +
                                      "\n\nReturn {\"id\": N}."), "{") or {}
        chosen = next((s for s in pending if s.id == obj.get("id")), None)
        if chosen:
            return chosen
    except Exception:  # noqa: BLE001
        pass
    return max(pending, key=lambda s: s.value())          # fallback: highest value


def reproduce(repo_dir, s):
    # LEAN context (root-cause fix for the 400 that crashed 6222): a reproduction targets ONE
    # suspicion, reading the actual code ON DEMAND via the tools. Passing the whole ~150k-char PR
    # context here overflowed max-model-len across the multi-turn agent — and was lost-in-the-middle.
    _reset_verdict()
    _sandbox.reset_clean()   # pristine source for THIS check — wipe what the previous reproducer wrote/built
    msg = (f"SUSPICION TO REPRODUCE:\nobservation: {s.observation}\nsuspected_bug: {s.suspected_bug}\n"
           f"location: {s.location}\n\n"
           "Try to REPRODUCE the bug by RUNNING code — reading is not reproduction. In `sandbox_exec`: either "
           "TEST (write a unit test/driver exercising the code, compile and run it — a FAILING run or compile "
           "error reproduces the bug) or LOG (add a log/print at the spot or in a driver, run it, read the "
           "output showing the wrong value/behavior). A clean run, or no runnable repro you can build, means "
           "REFUTE. You may edit /src/new (it auto-resets). Record any NEW bug you observe with add_suspicion. "
           "When done, call `record_verdict` (verdict, repro_kind test|log|none, reproduction = the command(s) "
           "run + their real output, evidence) — once, last.")
    out = _run_agent(REPRODUCER_SYS, msg, repo_dir,
                     extra_tools=[CAPTURE, "sandbox_exec", "record_verdict", "reset_workspace"])
    if _VERDICT.get("verdict") in ("confirmed", "refuted", "partial"):   # tool-captured: robust
        return dict(_VERDICT)
    j = _extract_json(out, "{")                                          # fallback: a JSON blob in text
    if isinstance(j, dict) and str(j.get("verdict", "")).lower() in ("confirmed", "refuted", "partial"):
        return {"verdict": str(j["verdict"]).lower(), "evidence": str(j.get("evidence", ""))}
    print(f"  [verdict] no record_verdict + no JSON for S[{s.id}] — defaulting refuted (not reproduced)", flush=True)
    return {"verdict": "refuted", "evidence": (out or "")[-300:], "repro_kind": "none"}


def solve(repo_dir, s):
    # Separate agent: only runs on a REPRODUCED bug. Full source edit (unlike the reproducer); graded by
    # re-running the reproducer's own check against its patch. Fresh, lean context — just the bug + how it
    # was shown, not the reproducer's whole exploration.
    _reset_fix()
    _sandbox.reset_clean()   # pristine source — the solver fixes from clean, not the reproducer's logging
    msg = (f"BUG TO FIX (already reproduced):\nobservation: {s.observation}\nsuspected_bug: {s.suspected_bug}\n"
           f"location: {s.location}\nhow it was shown ({s.repro_kind}): {s.evidence}\nreproduction:\n{s.reproduction}\n\n"
           "Change the real code in /src/new so this stops happening, then confirm by re-running the "
           "reproduction above against your change — the value should now come out right on /src/new with "
           "nothing else broken. Keep the change as small as you can. When done, call record_fix (fixed, "
           "fix_diff = your logic change, rerun = the output proving it). If you can't fix it, record fixed=false.")
    out = _run_agent(SOLVER_SYS, msg, repo_dir,
                     extra_tools=["sandbox_exec", "record_fix", "reset_workspace"])
    if "fixed" in _FIX:
        return dict(_FIX)
    return {"fixed": False, "fix_diff": "", "rerun": (out or "")[-300:]}


def synthesize(ctx, confirmed, partials):
    def _one(s):
        line = (f"- [{s.location}] {s.suspected_bug}\n    observation: {s.observation}\n"
                f"    reproduction ({s.repro_kind}): {s.evidence}")
        if s.fixed:
            line += f"\n    fix: {s.fix_diff[:400]}"
        return line
    body = "CONFIRMED FINDINGS (each REPRODUCED in the real code; some with a verified fix):\n" + (
        "\n".join(_one(s) for s in confirmed) or "(none)")
    if partials:
        body += "\n\nOPEN QUESTIONS (could not reproduce — include as hedged questions):\n" + "\n".join(
            f"- {s.suspected_bug} [{s.location}]" for s in partials)
    txt = _llm_call(SYNTHESIZER_SYS, "PULL REQUEST (context):\n" + ctx[:8000] + "\n\n" + body +
                    "\n\nWrite the review.")
    return final_review(_post_think(txt))


def run_suspicion_review(repo_dir, pr_input, conf_floor=0.4, max_checks=60, log=print):
    # LEAN context (Q2 / v10): the model gets the diff + the changed-files LIST and pulls full
    # file content on demand via pr_file_diff/file_editor — no pre-loaded blob. Verified: the lean
    # generator terminates cleanly (6222: 23 suspicions in ~9min, vs the fat blob's 17 — higher
    # recall) and the lean fact-check verifies one suspicion without overflowing the window.
    ctx = pr_input
    _reset_store()
    by_id = generate(repo_dir, ctx)           # generator writes suspicions to the store
    log(f"generated {len(by_id)} suspicions")
    for s in sorted(by_id.values(), key=lambda x: -x.value()):
        mark = "" if s.confidence >= conf_floor else "  (below conf floor, won't check)"
        log(f"   S[{s.id}] v={s.value():.1f} sev={s.severity} conf={s.confidence} :: {s.suspected_bug[:72]}{mark}")
    checks = 0
    while checks < max_checks:
        _store_to_suspicions(by_id)            # pick up any new suspicions the reproducer recorded
        # gate on CONFIDENCE (is it worth checking), not severity — a certain low-impact bug is
        # still a finding. Severity only sets the order (schedule()). The reproduction is the filter.
        pending = [s for s in by_id.values() if s.status == "pending" and s.confidence >= conf_floor]
        if not pending:
            break
        s = schedule(pending)
        before = len(_STORE)
        res = reproduce(repo_dir, s)
        s.status = str(res.get("verdict", "refuted")).lower()
        s.evidence = str(res.get("evidence", ""))[:600]
        s.repro_kind = str(res.get("repro_kind", ""))
        s.reproduction = str(res.get("reproduction", ""))[:600]
        checks += 1
        log(f"  check {checks}: [{s.id}] {s.status}/{s.repro_kind or '-'} (+{len(_STORE) - before} new) — {s.suspected_bug[:60]}")
        if s.status == "confirmed":           # reproduced -> hand to the SOLVER
            fx = solve(repo_dir, s)
            s.fixed = bool(fx.get("fixed"))
            s.fix_diff = str(fx.get("fix_diff", ""))[:600]
            s.fix_rerun = str(fx.get("rerun", ""))[:600]
            log(f"    solve [{s.id}]: {'FIXED' if s.fixed else 'no fix'}")
    confirmed = [s for s in by_id.values() if s.status == "confirmed"]
    partials = [s for s in by_id.values() if s.status == "partial"]
    refuted = sum(1 for s in by_id.values() if s.status == "refuted")
    solved = sum(1 for s in confirmed if s.fixed)
    log(f"=> confirmed {len(confirmed)} ({solved} fixed) | partial {len(partials)} | refuted {refuted} | "
        f"total suspicions {len(by_id)} | checks {checks}")
    review = synthesize(ctx, confirmed, partials)
    return review, list(by_id.values())


def _setup(repo, pr):
    """Resolve the PR, fetch the base repo, build the context, and point REASONING_LOG at
    this PR. Returns (repo_dir, pr_input, tag). Shared by run() and gen_probe()."""
    from current_version.repo import base_sha, ensure_repo
    from current_version.full_diff import full_pr_input
    from current_version import pr_diff_tool
    import dataset as ds
    imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values() for x in v}
    x = imap[(repo, int(pr))]
    pi = x["input"]
    bsha = base_sha(repo, pr)
    d = str(ensure_repo(repo, bsha))
    pi, ok = full_pr_input(pi, d, repo, pr, bsha)
    pr_diff_tool.set_pr(d, bsha, pr)
    files = pr_diff_tool.changed_files()
    if files:
        pi = re.sub(r'Changed files \((\d+)\):[^\n]*',
                    lambda m: f"Changed files ({m.group(1)}): " + ", ".join(files), pi, count=1)
    tag = repo.replace('/', '__') + '__' + str(pr)
    os.makedirs("results/reasoning", exist_ok=True)
    os.environ["REASONING_LOG"] = f"results/reasoning/{tag}.log"
    open(os.environ["REASONING_LOG"], "w").close()   # truncate per run; logs each agent turn's thinking
    return d, pi, tag


def gen_probe(repo, pr):
    """FAST inner-loop eval: run ONLY the generator and report how many suspicions it records
    and how long it took — so generator tuning (token cap / prompt) doesn't pay for fact-check."""
    import time as _t
    d, pi, _tag = _setup(repo, pr)
    _reset_store()
    t0 = _t.time()
    by_id = generate(d, pi)   # lean: diff + changed-files list; reads files on demand via tools
    print(f"\n=== GEN PROBE {repo}#{pr}: {len(by_id)} suspicions in {_t.time()-t0:.0f}s ===")
    for s in sorted(by_id.values(), key=lambda x: -x.value()):
        print(f"  S[{s.id}] sev={s.severity} conf={s.confidence} :: {s.suspected_bug[:80]}")
    return by_id


def run(repo, pr, conf_floor=0.4):
    d, pi, tag = _setup(repo, pr)
    os.makedirs("results/probes", exist_ok=True)
    _sandbox.start(repo, pr, log_path=f"results/probes/{tag}.log")
    try:
        review, sus = run_suspicion_review(d, pi, conf_floor=conf_floor)
    finally:
        _sandbox.stop()
    os.makedirs("results/susp_runs", exist_ok=True)
    out = {"repo": repo, "pr": pr, "review": review,
           "confirmed": sum(1 for s in sus if s.status == "confirmed"),
           "solved": sum(1 for s in sus if s.status == "confirmed" and s.fixed),
           "partial": sum(1 for s in sus if s.status == "partial"),
           "refuted": sum(1 for s in sus if s.status == "refuted"),
           "n_suspicions": len(sus),
           "suspicions": [asdict(s) for s in sus]}
    json.dump(out, open(f"results/susp_runs/{tag}.json", "w"), indent=1)
    print("\n=== REVIEW ===\n" + review)
    return review, sus


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "gen":
        gen_probe(sys.argv[1], int(sys.argv[2]))
    else:
        run(sys.argv[1], int(sys.argv[2]))
