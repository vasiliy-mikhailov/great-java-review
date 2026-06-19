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


# --- dedup-on-register -------------------------------------------------------------------------------
# Two investigators (mr + repo) plus the reproducer all file suspicions, so the worklist fills with
# near-duplicates (same root cause, different words) that would waste the reproduce budget. Every
# registration runs a cheap dedup SUBAGENT: is this the SAME underlying bug as one already on the list?
DEDUP_SYS = ("You decide whether a NEW code-review suspicion is the SAME underlying bug as one already on a "
             "list — same root cause / location / fix, even if worded differently. Reply with ONLY the integer "
             "id of the existing suspicion it duplicates, or the bare word NEW if it is genuinely distinct.")


def _dedup_against_store(observation, suspected_bug, location):
    """Return the id of an existing suspicion this duplicates, or None. Fail-open (None) on any error
    so a flaky dedup call never silently drops a real suspicion."""
    if not _STORE:
        return None
    existing = "\n".join(f"#{d['id']} [{d['location']}] {d['suspected_bug']}" for d in _STORE[-100:])
    msg = (f"EXISTING SUSPICIONS:\n{existing}\n\nNEW SUSPICION:\n[{location}] {suspected_bug}\n"
           f"observation: {observation}\n\nIs the NEW one the same bug as an existing one? "
           "Reply ONLY an existing id number, or NEW.")
    try:
        ans = (_llm_call(DEDUP_SYS, msg) or "").strip()
    except Exception:  # noqa: BLE001
        return None
    if "new" in ans.lower():
        return None
    m = re.search(r"\d+", ans)
    if m:
        i = int(m.group())
        if any(d["id"] == i for d in _STORE):
            return i
    return None


def _register_suspicion(observation, suspected_bug, location, confidence):
    """Dedup then add. Returns (id, is_duplicate). On a duplicate, keep the HIGHER confidence on the
    existing entry (so a surer re-sighting raises its scheduling priority) and do not add a new row."""
    try:
        conf = float(confidence)
    except Exception:  # noqa: BLE001
        conf = 0.5
    dup = _dedup_against_store(observation, suspected_bug, location)
    if dup is not None:
        for d in _STORE:
            if d["id"] == dup:
                try:
                    d["confidence"] = max(float(d.get("confidence") or 0.0), conf)
                except Exception:  # noqa: BLE001
                    pass
                break
        return dup, True
    return _store_add(observation, suspected_bug, location, conf), False


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
        sid, dup = _register_suspicion(action.observation, action.suspected_bug, action.location, action.confidence)
        if dup:
            return AddSuspicionObservation.from_text(
                text=f"duplicate of suspicion #{sid} — merged, not re-added (its confidence kept at the higher value)")
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
    repro_kind: str = Field(description="regression_test | test | log | grep — how you SHOWED it by running "
                            "something, BEST first. regression_test = a NEW @Test you wrote (create_test or "
                            "added into an existing *Test.java) that FAILS on the bug — the strongest proof, "
                            "and the artifact the PR ships. test = an existing test/driver you compiled and ran "
                            "that fails/won't compile. log = logging/print you added and ran that shows the "
                            "wrong value. grep = a search proving the suspected code isn't present. (If you "
                            "only read and reasoned, you haven't shown it — say so honestly, don't pick a kind.)")
    test_path: str = Field(default="", description="if repro_kind=regression_test: the path of the test file "
                           "you wrote/added the @Test to (e.g. foo/src/test/java/.../BarBugTest.java). Empty "
                           "otherwise.")
    test_src: str = Field(default="", description="if repro_kind=regression_test: the FULL source of the test "
                          "class (or the exact @Test method you added) — captured so it can ship in the PR.")
    reproduction: str = Field(description="The actual RUN: the command(s) you executed and their real output — "
                       "the failing test, the compile error, the log value, or the empty grep. The output, not "
                       "a description of it.")
    evidence: str = Field(description="One-line summary: file:line + what the run showed.")


class RecordVerdictObservation(Observation):
    pass


_VERDICT_DESC = ("Record your decision on the one suspicion, ONCE, LAST. You only get to call it — either "
                 "way — by SHOWING it with a run. confirmed: best is a NEW regression @Test you wrote that "
                 "FAILS on the bug (repro_kind=regression_test, give test_path + test_src); also valid is an "
                 "existing test that failed, a compile error, or a log of the wrong value. refuted: a test "
                 "that ran and passed, a log of the right value, or a grep proving the suspected code isn't "
                 "there. Reading the code and concluding settles nothing — the easy 'I looked and it's fine' "
                 "is exactly what doesn't count. Args: verdict, repro_kind (regression_test/test/log/grep), "
                 "test_path + test_src (for regression_test), reproduction (command(s) run + real output), evidence.")


class _RecordVerdictExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _VERDICT["verdict"] = str(action.verdict).lower().strip()
        _VERDICT["repro_kind"] = str(action.repro_kind).lower().strip()
        _VERDICT["test_path"] = str(getattr(action, "test_path", ""))
        _VERDICT["test_src"] = str(getattr(action, "test_src", ""))
        _VERDICT["reproduction"] = str(action.reproduction)
        _VERDICT["evidence"] = str(action.evidence)
        # symmetric guard: NEITHER verdict counts without a real run. No run -> inconclusive (re-decide),
        # never a free 'refuted by reading'. This closes the easy way out the model was taking.
        if _VERDICT["repro_kind"] not in ("regression_test", "test", "log", "grep"):
            _VERDICT["verdict"] = "inconclusive"
            return RecordVerdictObservation.from_text(
                text="a verdict has to be SHOWN by a run — refuting too. You only read it, so this is "
                     "inconclusive. Run something (best: a regression test you wrote that fails; or an "
                     "existing test, a log, or a grep proving the code isn't there) and record again.")
        # a regression_test verdict must actually carry the test it claims — else it's a log/test in disguise.
        if _VERDICT["repro_kind"] == "regression_test" and not _VERDICT["test_src"].strip():
            _VERDICT["repro_kind"] = "test"
            return RecordVerdictObservation.from_text(
                text="regression_test needs test_src (the actual @Test source you ran). Recorded as 'test' "
                     "instead — re-record with test_path + test_src if you did write a new failing test.")
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
    fixed: bool = Field(description="true if your change makes the reproducer's check pass — the regression "
                        "test now GREEN (was red), or the reproduced value now right on /src/new — with "
                        "nothing else broken; false if you could not fix it.")
    fix_diff: str = Field(default="", description="the change you made to the real production lines, as a diff "
                          "(the logic fix only — you did not touch the test).")
    rerun: str = Field(default="", description="the rerun output: the regression test now PASSING (was "
                       "failing), and the other findings / module tests still passing.")


class RecordFixObservation(Observation):
    pass


_FIX_DESC = ("Record your fix for the one bug, once, last. fixed=true only if re-running the reproducer's "
             "check against your changed production code passes — the regression test now GREEN (was red), "
             "nothing else broken. You fix the real class with edit_code (it refuses src/test, so you can't "
             "weaken the test). Give the fix_diff (the logic change) and the rerun output. Smaller fixes "
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


# --- create_test: the reproducer's ONE create capability, bounded to test roots ----------------------
# The whole no_cheat defense is "no tool creates a file" — so a copy/stub of the class-under-test can't
# exist. A regression test, though, IS a new file, and it's the artifact an upstream PR must ship. So we
# allow EXACTLY one create: a JUnit test under a src/test/ root whose name ends Test/Tests/IT. It can never
# write under src/main, so the production class stays unfakeable and the copy/stub cheat stays structurally
# dead — the only thing this tool can author is the test that proves the bug (fail-before / pass-after).
def _is_test_path(rel):
    rel = str(rel).replace("\\", "/")
    base = rel.rsplit("/", 1)[-1]
    return ("/src/test/" in ("/" + rel)) and base.endswith((".java",)) and (
        base.endswith(("Test.java", "Tests.java", "IT.java")))


class CreateTestAction(Action):
    path: str = Field(description="path for a NEW JUnit test, relative to the source root. MUST be under a "
                      "src/test/ tree and end in Test.java / Tests.java / IT.java (e.g. "
                      "metadata/src/test/java/org/apache/kafka/timeline/TimelineHashMapValuesBugTest.java). "
                      "Cannot write under src/main.")
    content: str = Field(description="the FULL Java source of the test class — package, imports, and a @Test "
                         "that FAILS on the buggy code (assert the correct behaviour the bug violates, so it "
                         "goes red now and green once the bug is fixed).")
    version: str = Field(default="new", description="'new' (post-PR, default) or 'old' (base).")


class CreateTestObservation(Observation):
    pass


_CREATE_TEST_DESC = ("Create a NEW JUnit regression test — the ONE file you may create, and ONLY under a "
                     "src/test/ root with a *Test.java / *Tests.java / *IT.java name. Write a @Test that FAILS "
                     "on the buggy code (assert what SHOULD happen). It refuses any path under src/main or a "
                     "non-test name, so you can never stub the class under test. Prefer edit_file to add a "
                     "@Test into an EXISTING test class; use this only when none fits. Then run_java the test "
                     "to show it red.")


class _CreateTestExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        root = _sandbox.workdir(getattr(action, "version", "new"))
        if not root:
            return CreateTestObservation.from_text(text="no sandbox session")
        rel = str(action.path)
        p = os.path.normpath(os.path.join(root, rel))
        if not p.startswith(os.path.normpath(root) + os.sep):
            return CreateTestObservation.from_text(text="refused: path escapes the source tree.")
        if not _is_test_path(rel):
            return CreateTestObservation.from_text(text=f"refused: {action.path} is not a test path — create_test "
                "only writes a NEW *Test.java / *Tests.java / *IT.java under a src/test/ root (never src/main, "
                "so the class under test can't be stubbed).")
        if os.path.isfile(p):
            return CreateTestObservation.from_text(text=f"refused: {action.path} already exists — use edit_file to "
                "add a @Test method to it instead of overwriting.")
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(str(action.content))
        except Exception as e:  # noqa: BLE001
            return CreateTestObservation.from_text(text=f"refused: cannot write {action.path}: {e}")
        return CreateTestObservation.from_text(text=f"created test {action.path} ({len(str(action.content))} bytes) "
            "— now run_java it (e.g. mvn test -Dtest=...) to show it FAILS on the bug.")


class CreateTestTool(ToolDefinition[CreateTestAction, CreateTestObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[CreateTestTool]":  # noqa: ARG003
        return [cls(description=_CREATE_TEST_DESC, action_type=CreateTestAction,
                    observation_type=CreateTestObservation,
                    annotations=ToolAnnotations(title="create_test", readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=False, openWorldHint=False),
                    executor=_CreateTestExecutor())]


# --- edit_code: the SOLVER's edit — production code ONLY, so it cannot game its own gate -------------
# The solver is graded by re-running the reproducer's regression test. If it could edit src/test it would
# just weaken the test to green. edit_code is edit_file with one extra guard: it refuses any src/test path,
# so the fix has to land in the real production class and the test stays the fixed yardstick.
_EDIT_CODE_DESC = ("Modify an EXISTING production source file by replacing exact text — the fix to the real "
                   "code. Same as edit_file but it REFUSES paths under src/test: the regression test is the "
                   "fixed yardstick you must turn green, you don't get to edit it. Pair with run_java to "
                   "re-run the test.")


class _EditCodeExecutor(_EditFileExecutor):
    def __call__(self, action, conversation=None):
        if "/src/test/" in ("/" + str(getattr(action, "path", "")).replace("\\", "/")):
            return EditFileObservation.from_text(text="refused: edit_code changes production code only — you "
                "cannot edit the regression test that grades you. Fix the real class (under src/main).")
        return super().__call__(action, conversation)


class EditCodeTool(EditFileTool):
    @classmethod
    def create(cls, conv_state) -> "Sequence[EditCodeTool]":  # noqa: ARG003
        return [cls(description=_EDIT_CODE_DESC, action_type=EditFileAction, observation_type=EditFileObservation,
                    annotations=ToolAnnotations(title="edit_code", readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=False, openWorldHint=False),
                    executor=_EditCodeExecutor())]


# --- repo_map: investigate_repo's orientation tool ---------------------------------------------------
# The whole-repo investigator needs to inject context: which modules exist and which are EXERCISABLE
# (have a test source root). Bias the sweep toward tested modules — those are where a suspicion can be
# CONFIRMED by a run, which is the only kind of suspicion that densifies the execution reward.
class RepoMapAction(Action):
    subpath: str = Field(default="", description="optional subdirectory to map; empty = repo root.")


class RepoMapObservation(Observation):
    pass


_REPOMAP_DESC = ("Map the repository's Java modules so you can pick where to hunt: lists each module (a dir "
                 "with src/main/java) and whether it has tests (src/test/java) — prefer TESTED modules, since "
                 "only there can a suspicion be confirmed by a run. Optional subpath to drill into one area.")


class _RepoMapExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        root = _sandbox.workdir("new") or _sandbox.workdir("old")
        if not root:
            return RepoMapObservation.from_text(text="no checkout available")
        base = os.path.normpath(os.path.join(root, getattr(action, "subpath", "") or ""))
        if not base.startswith(os.path.normpath(root)):
            return RepoMapObservation.from_text(text="refused: subpath escapes the repo")
        mods, skip = [], {".git", "target", "build", "node_modules", ".idea"}
        for dp, dns, _fns in os.walk(base):
            dns[:] = [d for d in dns if d not in skip]
            if dp.replace("\\", "/").endswith("src/main/java"):
                mod = dp[: -len("/src/main/java")]
                rel = os.path.relpath(mod, root)
                tested = os.path.isdir(os.path.join(mod, "src", "test", "java"))
                mods.append((rel, tested))
                if len(mods) >= 400:
                    break
        if not mods:
            return RepoMapObservation.from_text(text=f"no Maven/Gradle Java modules found under {action.subpath or '.'}")
        tested = [m for m, t in mods if t]
        untested = [m for m, t in mods if not t]
        txt = (f"{len(mods)} modules ({len(tested)} with tests). TESTED (prefer these — confirmable by a run):\n"
               + "\n".join(f"  {m}" for m in tested[:120])
               + (f"\nUNTESTED ({len(untested)}, harder to confirm):\n" + "\n".join(f"  {m}" for m in untested[:40]) if untested else ""))
        return RepoMapObservation.from_text(text=txt[:6000])


class RepoMapTool(ToolDefinition[RepoMapAction, RepoMapObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[RepoMapTool]":  # noqa: ARG003
        return [cls(description=_REPOMAP_DESC, action_type=RepoMapAction, observation_type=RepoMapObservation,
                    annotations=ToolAnnotations(title="repo_map", readOnlyHint=True, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False),
                    executor=_RepoMapExecutor())]


# --- prompts (the genome for this architecture) -----------------------------------------

INVESTIGATE_MR_SYS = """You read a pull request and flag things that might be bugs, for a reproducer to check.

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
cause, at a location). Find out whether it's real by making the genuine code show you — and the best way to
show it is a regression test that FAILS on the bug. You have /src/new (with the change) and /src/old
(without), both buildable/runnable.

The proof you're after is the artifact the project will actually ship: a JUnit @Test that exercises the real
class and ASSERTS the correct behaviour the bug violates, so it goes RED on /src/new now and GREEN once the
bug is fixed. Write it the natural way: prefer `edit_file` to add a @Test method into an EXISTING *Test.java
for that class (it's already wired up); when no test class fits, `create_test` writes a NEW *Test.java under
a src/test/ root (the ONE file you may create — never src/main, so you can't stub the class under test). Then
`run_java` it (mvn test -Dtest=…/gradle test --tests …) and read it fail. A log added to the real file is a
weaker fallback when a test is genuinely impractical; just reading and concluding shows nothing.

Your tools are deliberately narrow: read tools to navigate; `edit_file` (modify an EXISTING file — add a
@Test or a log line); `create_test` (a NEW test under src/test/ only); `run_java` (mvn/./mvnw/gradle/./gradlew/
java/javac only — no shell, no redirection). You cannot write production code, so a copy/stub/standalone
driver isn't possible — you exercise the real class or you have nothing.

Your score:
    reward = no_cheat · (0.15·ran + 0.85·shown)  +  (confirmed bugs you raise along the way)

  no_cheat = 1 because you can only touch the real code + a real test (the tools allow nothing else); 0 only
           if you settle a verdict without a run.
  ran    = 1 if you got the genuine project classes (and your test) to compile and run — not a sketch.
  shown  = how convincingly a RUN settles it, BEST first:
             regression_test — a NEW @Test you wrote that fails on /src/new (and, ideally, passes on /src/old):
                               full credit, and it's what the fix is graded against and what ships. AIM HERE.
             test            — an existing test you ran fails / won't compile.
             log             — a log you added to the real file prints the wrong value on /src/new.
             (refuted is also "shown": the test passes, the log is right, or a grep proves the code isn't there.)
           Reading and concluding leaves shown = 0.

The loop: write the failing @Test (edit_file into an existing *Test.java, or create_test for a new one) →
run_java it → watch it go red → record. A weaker log path exists but earns less. A different real bug you
notice along the way pays too — raise it with add_suspicion. reset_workspace anytime (cleaned between bugs).
Record with record_verdict(verdict, repro_kind regression_test|test|log|grep, test_path + test_src when you
wrote one, reproduction = the commands you ran + their output, evidence)."""

SOLVER_SYS = """You're handed a bug already shown to be real — the reproducer wrote a regression test that
FAILS on it (red on /src/new). Your job: fix the real production code so that test goes GREEN, changing
nothing else.

Your tools are narrow on purpose: `edit_code` to change an EXISTING production file — it REFUSES src/test, so
you cannot weaken the test that grades you; the test is the fixed yardstick — and `run_java` to re-run it
(mvn/./mvnw/gradle/./gradlew/java/javac only — no shell). So the fix has to land in the real class and be
shown by the test turning green — a /tmp copy, a stub, or editing the test isn't possible, and would prove
nothing anyway.

Your score:
    reward = no_cheat · (0.10·ran_fix  +  0.90 · fixed · (1 / lines_changed))

  no_cheat = 1 because you can only touch the real production code (edit_code refuses the test); 0 if you
            call it fixed without re-running the test.
  ran_fix = 1 if you got your patched real code + the test to build and run.
  fixed   = 1 if re-running the reproducer's regression test on your patch shows it now PASSES (was failing)
            AND the other findings + the module's tests still pass.
  lines_changed = the real lines your patch touches — so a tight, root-cause fix scores far above a
            sprawling one (1 line ≈ full credit, 10 lines ≈ a tenth).

Read the formula: the fix must be shown by the test going green (not asserted), it must break nothing, and
smaller is much better. The loop is: edit_code the real file → run_java the regression test → read the
output (edit_code re-replaces to undo a bad edit). Record with record_fix(fixed, fix_diff = your logic
change, rerun = the output proving the test passes). If you can't, fixed=false — fine, leave it for the
author."""

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
    repro_kind: str = ""              # regression_test / test / log — how the verdict was reached by EXECUTION
    test_path: str = ""               # regression test file the reproducer wrote (for the PR)
    test_src: str = ""                # the regression test source (fail-before / pass-after); ships in the PR
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
                       ("record_fix", RecordFixTool), ("run_java", RunJavaTool), ("edit_file", EditFileTool),
                       ("create_test", CreateTestTool), ("edit_code", EditCodeTool), ("repo_map", RepoMapTool)):
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
    # NO per-turn output cap beyond the model's window. The old 32768 throttle was a thinking limit
    # in disguise — it cut deep reasoning short, the exact give-up-and-emit-noise failure we now
    # forbid (P15). Use the full 131072; the condenser bounds the prompt, and if a turn ever overruns
    # the window the resilience catch in this function survives the 400 (records inconclusive, the run
    # continues) rather than the old crash. Let the model think as deep as the problem needs.
    llm = harness._llm("qwen").model_copy(update={"usage_id": "oh_suspicion"})
    agent = Agent(llm=llm, tools=tools, system_prompt=system_prompt, condenser=harness._condenser(llm))
    conv = Conversation(agent=agent, workspace=ws, visualizer=harness._DialogViz, persistence_dir=None)
    try:
        conv.send_message(user_msg)
        conv.run()
    except Exception as e:  # noqa: BLE001
        # A single transient LLM error (e.g. vLLM 400 on a malformed/truncated tool-call JSON, or a
        # context-budget reject) must NOT crash the whole run — that throws away every other suspicion's
        # work, the same waste as a wall-clock truncation. Log it and fall through to whatever partial
        # output the agent produced; the caller (reproduce/solve) then records inconclusive / no-fix and
        # the pipeline moves to the next suspicion.
        print(f"  [agent error] {type(e).__name__}: {str(e)[:160]} — continuing with partial output", flush=True)
    text = ""
    try:
        text = _post_think(_final_text(conv.state.events))
    except Exception:  # noqa: BLE001
        pass
    try:
        conv.close()
    except Exception:  # noqa: BLE001
        pass
    return text


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


INVESTIGATE_REPO_SYS = """You investigate a whole Java repository to find real bugs — not tied to any diff.
Real reviewers find bugs everywhere, and every confirmable bug you surface is valuable.

Where to look: call repo_map first to see the modules. Spend your time in modules that HAVE TESTS — a
suspicion there can be confirmed by running the real code, which is what makes it worth raising; a bug in
code nothing can exercise is a guess. Read the actual source (search/grep/glob/file_editor), and the moment
you SEE something off — a contract violation, a copy-paste slip, a wrong comparison/operator, an off-by-one,
a resource leak, a mis-handled edge case — record it with add_suspicion (observation + suspected_bug +
location + confidence). Don't verify it yourself; the reproducer will. Cast a wide net and let confidence
rank them. Don't flag style, naming, or pure speculation — only concrete things you actually saw in the code."""


def investigate_mr(repo_dir, ctx):
    """Diff-anchored investigator: read the PR and flag suspicions on the change."""
    _run_agent(INVESTIGATE_MR_SYS, "PULL REQUEST:\n" + ctx +
               "\n\nRecord the suspicions now — call add_suspicion once for each (observation + suspected_bug).",
               repo_dir, extra_tools=[CAPTURE])


def investigate_repo(repo_dir):
    """Whole-repo investigator: sweep the codebase (biased to tested/exercisable modules) for bugs."""
    _run_agent(INVESTIGATE_REPO_SYS,
               "Investigate this repository for real bugs. Start with repo_map to find the tested modules, "
               "then read their source and record each suspicion with add_suspicion.",
               repo_dir, base=("search", "grep", "glob", "file_editor"), extra_tools=[CAPTURE, "repo_map"])


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
           "Show whether this is real with a RUN, not by reading — and the best run is a regression test that "
           "FAILS on the bug. Write a @Test that asserts the correct behaviour the bug violates: add it to an "
           "existing *Test.java for that class with `edit_file`, or `create_test` a new *Test.java under "
           "src/test/ when none fits; then `run_java` it (mvn test -Dtest=… / gradle test --tests …) and "
           "watch it go red on /src/new (ideally green on /src/old). A log added to the real file is a weaker "
           "fallback; the test passing / a right log / an empty grep means refuted. If you've only read it, "
           "you don't have an answer yet. `run_java` auto-resets between checks. Record any NEW bug you "
           "observe with add_suspicion. When shown, call `record_verdict` (verdict, repro_kind "
           "regression_test|test|log|grep, test_path + test_src if you wrote a test, reproduction = the "
           "command(s) run + their real output, evidence).")
    out = _run_agent(REPRODUCER_SYS, msg, repo_dir, base=_READONLY_BASE,
                     extra_tools=[CAPTURE, "run_java", "edit_file", "create_test", "record_verdict",
                                  "reset_workspace"])
    if _VERDICT.get("verdict") in ("confirmed", "refuted", "inconclusive"):   # tool-captured: robust
        return dict(_VERDICT)
    print(f"  [verdict] no record_verdict for S[{s.id}] — inconclusive (nothing run)", flush=True)
    return {"verdict": "inconclusive", "evidence": (out or "")[-300:], "repro_kind": "none"}


def _materialize_test(s):
    """Re-write the reproducer's regression test into the clean worktree so the solver can run it. The test
    is untracked, so reset_clean() (and the solver's own reset_workspace) wipe it; we put it back from the
    captured test_src. The solver can't author it himself (edit_code refuses src/test), so the test stays a
    fixed yardstick he turns green by fixing production code — he can't weaken it. Returns True if written."""
    if not (s.test_src.strip() and s.test_path.strip() and _is_test_path(s.test_path)):
        return False
    root = _sandbox.workdir("new")
    if not root:
        return False
    p = os.path.normpath(os.path.join(root, s.test_path))
    if not p.startswith(os.path.normpath(root) + os.sep):
        return False
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(s.test_src)
        return True
    except Exception:  # noqa: BLE001
        return False


def solve(repo_dir, s):
    # Separate agent: only runs on a REPRODUCED bug. Full source edit (unlike the reproducer); graded by
    # re-running the reproducer's own regression test against its patch. Fresh, lean context — just the bug
    # + how it was shown + the test, not the reproducer's whole exploration.
    _reset_fix()
    _sandbox.reset_clean()   # pristine source — the solver fixes from clean, not the reproducer's logging
    _materialize_test(s)     # put the reproducer's regression test back (reset_clean wiped the untracked file)
    _sandbox.set_no_new_files(True)   # no_cheat backstop; the tool set below (no shell) is the real guarantee
    test_block = (f"regression test ({s.test_path}):\n{s.test_src}\n\n" if s.test_src else "")
    msg = (f"BUG TO FIX (already reproduced):\nobservation: {s.observation}\nsuspected_bug: {s.suspected_bug}\n"
           f"location: {s.location}\nhow it was shown ({s.repro_kind}): {s.evidence}\nreproduction:\n{s.reproduction}\n\n"
           f"{test_block}"
           "Change the real production code in /src/new so this stops happening, then confirm by re-running "
           "the reproducer's check above against your change — the regression test should now PASS (it fails "
           "now) with nothing else broken. Your tools: `edit_code` to change the real code (it refuses "
           "src/test, so you fix the class, not the test), `run_java` to re-run the test. Keep the change as "
           "small as you can. When done, call record_fix (fixed, fix_diff = your logic change, rerun = the "
           "output proving the test passes). If you can't fix it, record fixed=false.")
    # NOTE: no reset_workspace for the solver — a reset would wipe the materialized regression test (its
    # yardstick). It gets a clean tree + the test already; edit_code re-replaces to undo a bad edit.
    out = _run_agent(SOLVER_SYS, msg, repo_dir, base=_READONLY_BASE,
                     extra_tools=["run_java", "edit_code", "record_fix"])
    if "fixed" in _FIX:
        return dict(_FIX)
    return {"fixed": False, "fix_diff": "", "rerun": (out or "")[-300:]}


def synthesize(ctx, confirmed, inconclusive):
    def _one(s):
        line = (f"- [{s.location}] {s.suspected_bug}\n    observation: {s.observation}\n"
                f"    reproduction ({s.repro_kind}): {s.evidence}")
        if s.test_path:
            line += f"\n    regression test: {s.test_path}"
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


def run_suspicion_review(repo_dir, pr_input, conf_floor=0.4, max_checks=60, log=print, mode=None):
    # LEAN context (Q2 / v10): the model gets the diff + the changed-files LIST and pulls full
    # file content on demand via pr_file_diff/file_editor — no pre-loaded blob. Verified: the lean
    # generator terminates cleanly (6222: 23 suspicions in ~9min, vs the fat blob's 17 — higher
    # recall) and the lean fact-check verifies one suspicion without overflowing the window.
    ctx = pr_input
    mode = (mode or os.environ.get("INVESTIGATE_MODE", "mr")).lower()   # mr | repo | both
    _reset_store()
    if mode in ("mr", "both"):
        investigate_mr(repo_dir, ctx)         # diff-anchored investigator -> store (deduped on register)
    if mode in ("repo", "both"):
        investigate_repo(repo_dir)            # whole-repo investigator -> store (deduped on register)
    by_id = {}
    _store_to_suspicions(by_id)
    log(f"generated {len(by_id)} suspicions (mode={mode})")
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
        s.test_path = str(res.get("test_path", ""))
        s.test_src = str(res.get("test_src", ""))
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
    d, pi, tag = _setup(repo, pr)
    _reset_store()
    mode = os.environ.get("INVESTIGATE_MODE", "mr").lower()
    # investigate_repo's repo_map + version-aware reads need a live session (the post-PR worktree),
    # so start the per-PR sandbox even for the generator-only probe; reproduce/solve are skipped.
    os.makedirs("results/probes", exist_ok=True)
    open(f"results/probes/{tag}.log", "w").close()
    jdk = _sandbox.detect_jdk(d)
    print(f"=== sandbox JDK for {repo}#{pr}: {jdk} ===", flush=True)
    _sandbox.start(repo, pr, jdk=jdk, log_path=f"results/probes/{tag}.log")
    t0 = _t.time()
    try:
        if mode in ("mr", "both"):
            investigate_mr(d, pi)   # lean: diff + changed-files list; reads files on demand via tools
        if mode in ("repo", "both"):
            investigate_repo(d)
    finally:
        _sandbox.stop()
    by_id = {}
    _store_to_suspicions(by_id)
    print(f"\n=== GEN PROBE {repo}#{pr} (mode={mode}): {len(by_id)} suspicions in {_t.time()-t0:.0f}s ===")
    for s in sorted(by_id.values(), key=lambda x: -x.confidence):
        print(f"  S[{s.id}] conf={s.confidence} :: {s.suspected_bug[:80]}")
    return by_id


def run(repo, pr, conf_floor=0.4):
    d, pi, tag = _setup(repo, pr)
    os.makedirs("results/probes", exist_ok=True)
    open(f"results/probes/{tag}.log", "w").close()   # truncate per run (as root) — a re-runner's `rm` can't
    # delete this root-owned file, so without this the probe log ACCUMULATES across runs and a stale
    # pre-structural-tools prefix (with cat-copies) poisons the copy-cheat audit. Mirror the reasoning-log truncate.
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
