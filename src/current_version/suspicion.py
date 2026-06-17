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


def _store_add(observation, suspected_bug, location, confidence):
    sid = len(_STORE)
    _STORE.append({"id": sid, "observation": str(observation), "suspected_bug": str(suspected_bug),
                   "location": str(location), "confidence": confidence})
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
    confidence: float = Field(description="0-1, how sure you are this is a real bug, before it's reproduced.")


class AddSuspicionObservation(Observation):
    pass


_ADD_DESC = ("Record ONE suspicion — an OBSERVATION (something you literally saw that looks off) plus the "
             "suspected_bug it might cause. A candidate for the REPRODUCER to reproduce later, NOT a confirmed "
             "finding. Raise it the MOMENT something looks off; do not verify it yourself. Skip pure chores "
             "('verify X') and pure speculation ('might be slow'). Call once per suspicion. "
             "Args: observation, suspected_bug, location, confidence (0-1, how sure you are).")


class _AddSuspicionExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        sid = _store_add(action.observation, action.suspected_bug, action.location, action.confidence)
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
    verdict: str = Field(description="confirmed | refuted — and EITHER way it has to be shown by a RUN. "
                         "confirmed: a test you ran FAILED / wouldn't compile, or your log shows the wrong "
                         "value. refuted: the test you ran PASSED / the log shows the right value (or a grep "
                         "proves the suspected code/symbol isn't even there). Reading the code and deciding "
                         "doesn't settle it either way.")
    repro_kind: str = Field(description="test | log | grep — how you SHOWED it by running something. test = a "
                            "test/driver you compiled and ran. log = logging/print you added and ran. grep = a "
                            "search proving the suspected code isn't present. (If you only read and reasoned, "
                            "you haven't shown it — say so honestly rather than picking a kind.)")
    reproduction: str = Field(description="The actual RUN: the command(s) you executed and their real output — "
                       "the failing/passing test, the compile error, the log value, or the empty grep. The "
                       "output, not a description of it.")
    evidence: str = Field(description="One-line summary: file:line + what the run showed.")


class RecordVerdictObservation(Observation):
    pass


_VERDICT_DESC = ("Record your decision on the one suspicion, ONCE, LAST. You only get to call it — either "
                 "way — by SHOWING it with a run. confirmed: a test that ran and failed, a compile error, or "
                 "a log of the wrong value. refuted: a test that ran and passed, a log of the right value, or "
                 "a grep proving the suspected code isn't there. Reading the code and concluding settles "
                 "nothing — the easy 'I looked and it's fine' is exactly what doesn't count. "
                 "Args: verdict, repro_kind (test/log/grep), reproduction (the command(s) run + real output), evidence.")


class _RecordVerdictExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _VERDICT["verdict"] = str(action.verdict).lower().strip()
        _VERDICT["repro_kind"] = str(action.repro_kind).lower().strip()
        _VERDICT["reproduction"] = str(action.reproduction)
        _VERDICT["evidence"] = str(action.evidence)
        # symmetric guard: NEITHER verdict counts without a real run. No run -> inconclusive (re-decide),
        # never a free 'refuted by reading'. This closes the easy way out the model was taking.
        if _VERDICT["repro_kind"] not in ("test", "log", "grep"):
            _VERDICT["verdict"] = "inconclusive"
            return RecordVerdictObservation.from_text(
                text="a verdict has to be SHOWN by a run — refuting too. You only read it, so this is "
                     "inconclusive. Run something (a test, a log, or a grep proving the code isn't there) "
                     "and record again.")
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


# --- run_java + edit_file: the REPRODUCER's structured tools (replaces sandbox_exec) -----------------
# sandbox_exec (arbitrary bash) let the reproducer write a COPY of a class and "reproduce" off it. Take it
# away and give exactly two levers: edit_file (modify an EXISTING file — add logging) and run_java (run
# mvn/gradle/java/javac, no shell). A copy/stub/driver is then structurally impossible — no tool creates a file.
class RunJavaAction(Action):
    command: str = Field(description="a build/run command — mvn / ./mvnw / gradle / ./gradlew / java / javac "
                         "against the REAL files. No shell redirection, pipes, or file-writing; to change "
                         "code use edit_file.")
    version: str = Field(default="new", description="'new' (post-PR, default) or 'old' (base).")


class RunJavaObservation(Observation):
    pass


_RUNJAVA_DESC = ("Run the project's tests/build or compile/run the REAL classes: mvn / ./mvnw / gradle / "
                 "./gradlew / java / javac. Returns exit code + output. Runs only those programs and rejects "
                 "shell redirection / file-writing — you cannot create files here (use edit_file to modify an "
                 "existing one). This is how you exercise the real code after adding logging.")
_RUNJAVA_OK = {"mvn", "./mvnw", "mvnw", "gradle", "./gradlew", "gradlew", "java", "javac"}
_RUNJAVA_BAD = (">", "|", ";", "&&", "||", "`", "$(", "<<", "cat ", "tee", " cp ", " mv ", "touch ",
                "mkdir", "echo ", "printf", "ln ", "dd ", "rsync")


class _RunJavaExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        cmd = str(action.command).strip()
        first = cmd.split()[0] if cmd else ""
        if first not in _RUNJAVA_OK or any(b in cmd for b in _RUNJAVA_BAD):
            return RunJavaObservation.from_text(text="rejected: run_java only runs mvn/gradle/java/javac with no "
                "shell redirection or file-writing. To change code use edit_file (existing files only).")
        rc, out = _sandbox.exec_(cmd, version=getattr(action, "version", "new"))
        return RunJavaObservation.from_text(text=f"exit={rc}\n{out}")


class RunJavaTool(ToolDefinition[RunJavaAction, RunJavaObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[RunJavaTool]":  # noqa: ARG003
        return [cls(description=_RUNJAVA_DESC, action_type=RunJavaAction, observation_type=RunJavaObservation,
                    annotations=ToolAnnotations(title="run_java", readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=False, openWorldHint=True),
                    executor=_RunJavaExecutor())]


class EditFileAction(Action):
    path: str = Field(description="path of an EXISTING file relative to the source root (e.g. "
                      "core/runtime/src/main/java/io/quarkus/runtime/Foo.java) to modify.")
    find: str = Field(description="exact existing text to replace (must appear verbatim in the file).")
    replace: str = Field(description="the new text (e.g. the same line plus a log statement).")
    version: str = Field(default="new", description="'new' (post-PR, default) or 'old' (base).")


class EditFileObservation(Observation):
    pass


_EDIT_DESC = ("Modify an EXISTING source file by replacing exact text — e.g. add a log line. It CANNOT create "
              "files and refuses if the file or the find-text is absent, so you can only instrument the real "
              "code, never write a copy. Pair with run_java to exercise it.")


class _EditFileExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        root = _sandbox.workdir(getattr(action, "version", "new"))
        if not root:
            return EditFileObservation.from_text(text="no sandbox session")
        p = os.path.normpath(os.path.join(root, str(action.path)))
        if not p.startswith(os.path.normpath(root) + os.sep):
            return EditFileObservation.from_text(text="refused: path escapes the source tree.")
        if not os.path.isfile(p):
            return EditFileObservation.from_text(text=f"refused: {action.path} does not exist — edit_file only "
                "MODIFIES existing files, it cannot create new ones.")
        try:
            s = open(p, errors="ignore").read()
        except Exception as e:  # noqa: BLE001
            return EditFileObservation.from_text(text=f"refused: cannot read {action.path}: {e}")
        if str(action.find) not in s:
            return EditFileObservation.from_text(text=f"refused: the find-text was not found in {action.path}.")
        open(p, "w").write(s.replace(str(action.find), str(action.replace), 1))
        return EditFileObservation.from_text(text=f"edited {action.path} (1 replacement).")


class EditFileTool(ToolDefinition[EditFileAction, EditFileObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[EditFileTool]":  # noqa: ARG003
        return [cls(description=_EDIT_DESC, action_type=EditFileAction, observation_type=EditFileObservation,
                    annotations=ToolAnnotations(title="edit_file", readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=False, openWorldHint=False),
                    executor=_EditFileExecutor())]


# --- prompts (the genome for this architecture) -----------------------------------------

SUSPECTOR_SYS = """You read a pull request and flag things that might be bugs, for a reproducer to check.

Your score:
    reward = Σ confidence(s)  over your suspicions that get CONFIRMED

You bank the confidence you stated, but only on the ones that turn out real. A suspicion that gets refuted
costs nothing (it just scores 0), and one pointing at code that isn't in the diff can't be confirmed at
all, so it scores 0 too — there's no penalty for either, so flag generously: a bug you miss is gone for
good, an extra guess is free. The only thing that pays is a real bug you surfaced — and more when you were
sure of it. So put high confidence on what you genuinely believe, lower on the long shots; be honest, since
honest confidence is also what gets the surest ones reproduced first.

Flag each the moment you see it with add_suspicion(observation = the specific thing you saw, suspected_bug =
the bug it might cause, location, confidence). Don't keep them in your head; sweep the whole diff."""

REPRODUCER_SYS = """You're given one suspected bug in a Java project (an observation + the problem it might
cause, at a location). Find out whether it's real by making the genuine code show you. You have /src/new
(with the change) and /src/old (without), both buildable/runnable.

Your tools are deliberately narrow: read tools to navigate; `edit_file` to add a log line into an EXISTING
file (it cannot create files); `run_java` to run the project's tests/build or javac/java the real classes
(mvn/./mvnw/gradle/./gradlew/java/javac only — no shell, no redirection). There is no way to write a new
file, so a copy/stub/standalone driver simply isn't possible — you instrument and run the real code or you
have nothing.

Your score:
    reward = no_cheat · (0.15·ran + 0.85·shown)  +  (confirmed bugs you raise along the way)

  no_cheat = 1 because you can only touch the real code (the tools allow nothing else); it is 0 only if you
           settle a verdict without a run.
  ran    = 1 if you got the genuine project classes to compile and run (an existing test, or javac/java of
           the real classes — not a sketch).
  shown  = 1 if a RUN settles it. REAL: an existing test you ran fails / won't compile, or a log you added
           with edit_file to the real file prints the wrong value — ideally wrong on /src/new, right on
           /src/old. NOT REAL: the test passes, the log is right, or a grep shows the suspected code isn't
           there. Reading and concluding leaves shown = 0.

Read the formula: reasoning your way to an answer earns nothing (shown stays 0); getting the real code to
build and run is worth a little on its own (ran); a run that settles it is the bulk (shown); a different real
bug you notice and raise with add_suspicion pays too. The loop is: edit_file to add a log to the real file →
run_java an existing test/entry point that exercises it → read the output. reset_workspace anytime (cleaned
between bugs). Record with record_verdict(verdict, repro_kind test|log|grep, reproduction = the commands you
ran + their output, evidence)."""

SOLVER_SYS = """You're handed a bug already shown to be real — the reproducer's logging shows a value wrong
on /src/new and right on /src/old, with the driver that triggers it. Fix the real code so it's gone.

Your tools are narrow on purpose: `edit_file` to change an EXISTING file (it cannot create files) and
`run_java` to build/re-run (mvn/./mvnw/gradle/./gradlew/java/javac only — no shell). So the fix has to go
into the real code and be shown by re-running the real check — a /tmp copy or a standalone sketch isn't
possible, and proving the fix on one would prove nothing.

Your score:
    reward = no_cheat · (0.10·ran_fix  +  0.90 · fixed · (1 / lines_changed))

  no_cheat = 1 because you can only touch the real code (the tools allow nothing else); 0 if you call it
            fixed without re-running the real check.
  ran_fix = 1 if you got your patched real code to build and run.
  fixed   = 1 if re-running the reproducer's check on your patch shows the value now correct AND the other
            findings + the module's tests still pass.
  lines_changed = the real lines your patch touches — so a tight, root-cause fix scores far above a
            sprawling one (1 line ≈ full credit, 10 lines ≈ a tenth).

Read the formula: the fix must be shown by re-running the check (not asserted), it must break nothing, and
smaller is much better. The loop is: edit_file the real file → run_java the reproduction → read the output.
reset_workspace anytime. Record with record_fix(fixed, fix_diff = your logic change, rerun = the output
proving it). If you can't, fixed=false — fine, leave it for the author."""

SYNTHESIZER_SYS = """You write the final Java code review from CONFIRMED findings only — each one a bug the
reproducer showed in the real code, some with a fix the solver verified. Turn each into a point with its
file:line, what the bug is, and the fix if there is one. Add no new claims of your own. A short, sharp
review beats a flood. Output SUMMARY: then POINTS:, each as - [path/File.java:line] <bug> [— fix: <fix>]."""


@dataclass
class Suspicion:
    id: int
    observation: str                  # what the suspector literally saw
    suspected_bug: str                # the bug it might cause (hypothesis)
    location: str
    confidence: float                 # how sure the model is — the ONLY priority signal (check surest first)
    status: str = "pending"           # pending / confirmed / refuted / inconclusive
    evidence: str = ""
    repro_kind: str = ""              # test / log — how the verdict was reached by EXECUTION (none = inconclusive)
    reproduction: str = ""            # the actual run: command(s) + their output
    fixed: bool = False               # solver verified a fix (only attempted on confirmed bugs)
    fix_diff: str = ""                # the logic change the solver made to the real lines
    fix_rerun: str = ""               # the rerun output proving the fix + nothing else broken


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
                       ("record_fix", RecordFixTool), ("run_java", RunJavaTool), ("edit_file", EditFileTool)):
            try:
                _register_tool(_n, _t)
            except Exception:  # noqa: BLE001  (already registered)
                pass
        _TOOLS_READY = True
    return [Tool(name=n) for n in ("search", "grep", "glob", "file_editor", "pr_files", "pr_file_diff")]


# read tools that can only READ (no file_editor — which can `create` a copy). The reproducer gets these
# plus edit_file (modify existing) + run_java (run, no shell) — so a copy/stub/driver has no tool to exist.
_READONLY_BASE = ("search", "grep", "glob", "pr_files", "pr_file_diff")


CAPTURE = "add_suspicion"


def _run_agent(system_prompt, user_msg, repo_dir, extra_tools=(), version="new", base=None):
    """Run a tool-using agent to completion; return its final (post-think) text. The read
    tools (search/grep/glob/file_editor) are rooted at the agent's workspace, which we point
    at the POST-PR tree by default (version='new') so added/renamed files are on disk and
    searchable — base-only was the dominant cause of under-confirming. `version='old'` (or no
    live sandbox session) falls back to the base checkout. `base` overrides the read-tool set —
    the reproducer passes _READONLY_BASE (no file_editor) so it cannot create a copy."""
    ws = _sandbox.workdir(version) or str(repo_dir)
    base_tools = [Tool(name=n) for n in base] if base is not None else _read_tools()
    if base is not None:
        _read_tools()    # ensure run_java/edit_file/etc are registered even when overriding the base set
    tools = base_tools + [Tool(name=n) for n in extra_tools]
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
                                           confidence=float(d["confidence"]))
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
    # Check what the model is SUREST of first. Confidence is the only priority signal — deterministic,
    # no LLM call, no severity (the suspector's severity was noise: it stamped speculative concerns
    # 'critical' and its surest real bug 'low', burying the real one).
    return max(pending, key=lambda s: s.confidence)


def reproduce(repo_dir, s):
    # LEAN context (root-cause fix for the 400 that crashed 6222): a reproduction targets ONE
    # suspicion, reading the actual code ON DEMAND via the tools. Passing the whole ~150k-char PR
    # context here overflowed max-model-len across the multi-turn agent — and was lost-in-the-middle.
    _reset_verdict()
    _sandbox.reset_clean()   # pristine source for THIS check — wipe what the previous reproducer wrote/built
    _sandbox.set_no_new_files(True)   # no_cheat backstop; the real guarantee is the tool set below (no shell)
    msg = (f"SUSPICION TO REPRODUCE:\nobservation: {s.observation}\nsuspected_bug: {s.suspected_bug}\n"
           f"location: {s.location}\n\n"
           "Make the real code show you whether this is real, then say which way — but only from a run, not "
           "from reading. Real: a test you ran fails / won't compile, or a log you added prints the wrong "
           "value (ideally wrong on /src/new, right on /src/old). Not real: the test you ran passes, the log "
           "is right, or a grep shows the suspected code isn't even there. If you've only read it, you don't "
           "have an answer yet. Your tools: `edit_file` to add a log line to an EXISTING file, and `run_java` "
           "to run the project's tests/build or javac/java the real classes (it auto-resets between checks). "
           "Record any NEW bug you observe with add_suspicion. When the code has shown you, call "
           "`record_verdict` (verdict, repro_kind test|log|grep, reproduction = the command(s) run + their "
           "real output, evidence).")
    out = _run_agent(REPRODUCER_SYS, msg, repo_dir, base=_READONLY_BASE,
                     extra_tools=[CAPTURE, "run_java", "edit_file", "record_verdict", "reset_workspace"])
    if _VERDICT.get("verdict") in ("confirmed", "refuted", "inconclusive"):   # tool-captured: robust
        return dict(_VERDICT)
    print(f"  [verdict] no record_verdict for S[{s.id}] — inconclusive (nothing run)", flush=True)
    return {"verdict": "inconclusive", "evidence": (out or "")[-300:], "repro_kind": "none"}


def solve(repo_dir, s):
    # Separate agent: only runs on a REPRODUCED bug. Full source edit (unlike the reproducer); graded by
    # re-running the reproducer's own check against its patch. Fresh, lean context — just the bug + how it
    # was shown, not the reproducer's whole exploration.
    _reset_fix()
    _sandbox.reset_clean()   # pristine source — the solver fixes from clean, not the reproducer's logging
    _sandbox.set_no_new_files(True)   # no_cheat backstop; the tool set below (no shell) is the real guarantee
    msg = (f"BUG TO FIX (already reproduced):\nobservation: {s.observation}\nsuspected_bug: {s.suspected_bug}\n"
           f"location: {s.location}\nhow it was shown ({s.repro_kind}): {s.evidence}\nreproduction:\n{s.reproduction}\n\n"
           "Change the real code in /src/new so this stops happening, then confirm by re-running the "
           "reproduction above against your change — the value should now come out right on /src/new with "
           "nothing else broken. Your tools: `edit_file` to change the real code, `run_java` to re-run the "
           "reproduction (an existing test, or javac/java the real classes). Keep the change as small as you "
           "can. When done, call record_fix (fixed, fix_diff = your logic change, rerun = the output proving "
           "it). If you can't fix it, record fixed=false.")
    out = _run_agent(SOLVER_SYS, msg, repo_dir, base=_READONLY_BASE,
                     extra_tools=["run_java", "edit_file", "record_fix", "reset_workspace"])
    if "fixed" in _FIX:
        return dict(_FIX)
    return {"fixed": False, "fix_diff": "", "rerun": (out or "")[-300:]}


def synthesize(ctx, confirmed, inconclusive):
    def _one(s):
        line = (f"- [{s.location}] {s.suspected_bug}\n    observation: {s.observation}\n"
                f"    reproduction ({s.repro_kind}): {s.evidence}")
        if s.fixed:
            line += f"\n    fix: {s.fix_diff[:400]}"
        return line
    body = "CONFIRMED FINDINGS (each REPRODUCED in the real code; some with a verified fix):\n" + (
        "\n".join(_one(s) for s in confirmed) or "(none)")
    if inconclusive:
        body += "\n\nOPEN QUESTIONS (couldn't be settled by a run — include as hedged questions):\n" + "\n".join(
            f"- {s.suspected_bug} [{s.location}]" for s in inconclusive)
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
    for s in sorted(by_id.values(), key=lambda x: -x.confidence):   # surest first — confidence is the order
        mark = "" if s.confidence >= conf_floor else "  (below conf floor, won't check)"
        log(f"   S[{s.id}] conf={s.confidence} :: {s.suspected_bug[:80]}{mark}")
    checks = 0
    while checks < max_checks:
        _store_to_suspicions(by_id)            # pick up any new suspicions the reproducer recorded
        # confidence is the only signal: check what the model is SUREST of first, down to the floor.
        pending = [s for s in by_id.values() if s.status == "pending" and s.confidence >= conf_floor]
        if not pending:
            break
        s = schedule(pending)
        before = len(_STORE)
        res = reproduce(repo_dir, s)
        s.status = str(res.get("verdict", "inconclusive")).lower()
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
    inconclusive = [s for s in by_id.values() if s.status == "inconclusive"]
    refuted = sum(1 for s in by_id.values() if s.status == "refuted")
    solved = sum(1 for s in confirmed if s.fixed)
    log(f"=> confirmed {len(confirmed)} ({solved} fixed) | inconclusive {len(inconclusive)} | "
        f"refuted {refuted} | total {len(by_id)} | checks {checks}")
    review = synthesize(ctx, confirmed, inconclusive)
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
    for s in sorted(by_id.values(), key=lambda x: -x.confidence):
        print(f"  S[{s.id}] conf={s.confidence} :: {s.suspected_bug[:80]}")
    return by_id


def run(repo, pr, conf_floor=0.4):
    d, pi, tag = _setup(repo, pr)
    os.makedirs("results/probes", exist_ok=True)
    jdk = _sandbox.detect_jdk(d)
    print(f"=== sandbox JDK for {repo}#{pr}: {jdk} ===", flush=True)
    _sandbox.start(repo, pr, jdk=jdk, log_path=f"results/probes/{tag}.log")
    try:
        review, sus = run_suspicion_review(d, pi, conf_floor=conf_floor)
    finally:
        _sandbox.stop()
    os.makedirs("results/susp_runs", exist_ok=True)
    out = {"repo": repo, "pr": pr, "review": review,
           "confirmed": sum(1 for s in sus if s.status == "confirmed"),
           "solved": sum(1 for s in sus if s.status == "confirmed" and s.fixed),
           "inconclusive": sum(1 for s in sus if s.status == "inconclusive"),
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
