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
from dataclasses import dataclass, asdict, field

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

# --- THE REGISTRY: three linked entry types, each stage writes the next ------------------------------
# suspicion (investigator) -> bug (reproducer: PROVEN by a unit test it ran) -> solution (solver: verified
# fix). Each is a first-class entry with its own attributes; an agent reads the prior stage's entries and
# appends to the next. The PR writer reads all three. _STORE holds suspicions as dicts (the add_suspicion
# tool writes plain dicts, deduped); _BUGS / _SOLUTIONS hold dataclass entries.
_STORE = []        # suspicions: {id, observation, suspected_bug, location, confidence}
_BUGS = []         # proven bugs (Bug entries) — one per reproduced suspicion
_SOLUTIONS = []    # verified fixes (Solution entries) — one per solved bug


def _reset_store():
    _STORE.clear()
    _BUGS.clear()
    _SOLUTIONS.clear()


def _store_add(observation, suspected_bug, location, confidence):
    sid = len(_STORE)
    _STORE.append({"id": sid, "observation": str(observation), "suspected_bug": str(suspected_bug),
                   "location": str(location), "confidence": confidence})
    return sid


def _add_bug(suspicion, verdict, validation=""):
    """Promote a gate-passed suspicion into a Bug registry entry from the reproducer's verdict dict."""
    b = Bug(id=len(_BUGS), suspicion_id=suspicion.id, observation=suspicion.observation,
            suspected_bug=suspicion.suspected_bug, location=suspicion.location,
            repro_kind=str(verdict.get("repro_kind", "")), evidence=str(verdict.get("evidence", ""))[:600],
            reproduction=str(verdict.get("reproduction", ""))[:2000],
            bug_trace=str(verdict.get("bug_trace", ""))[:3500],
            test_path=str(verdict.get("test_path", "")), test_src=str(verdict.get("test_src", "")),
            test_cmd=str(verdict.get("test_cmd", "")), validation=str(validation),
            build_edit_path=str(verdict.get("build_edit_path", "")),
            build_edit_src=str(verdict.get("build_edit_src", "")),
            test_files=dict(verdict.get("test_files", {})))
    _BUGS.append(b)
    return b


def _add_solution(bug, fix):
    """Record the solver's outcome for a bug as a Solution registry entry, with the reward computed from
    MEASURED inputs (not the model's self-report):
        reward = passes · 0.9^lines_changed · (test_changed ? 0 : 1)
    passes requires a real test that the solver turned green AND a captured green run (fix_trace from run_java —
    a grep-only bug has no test -> 0; a "fixed" claim with no real green run -> 0). lines_changed is the
    production patch size measured from git in solve(); test_changed is whether the solver edited the test
    itself (disk vs the materialized test). Touch the test -> 0; the smaller the real fix, the higher."""
    diff = str(fix.get("fix_diff", ""))
    fixed = bool(fix.get("fixed"))
    lines = int(fix.get("lines_changed", 0) or 0)
    test_changed = bool(fix.get("test_changed", False))
    # fix_trace = the AUTHORITATIVE green run (Tests run … Failures: 0 + BUILD SUCCESS), captured from
    # run_java AND BOUND to THIS bug's own test (selector from test_cmd/test_path). Recomputed from _RUNS
    # here, not trusted from the model: a green run of some OTHER already-passing test must not count as
    # proof, or a no-op "fix" that just runs an unrelated green test would score 1.0. No real green run for
    # this test -> no proof -> reward 0. The reward is gated on it, not on the model's "fixed" word.
    fix_trace = _last_pass_trace(_selector(bug.test_cmd, bug.test_path))
    trace_ok = bool(fix_trace)
    passes = fixed and bool(bug.test_src) and trace_ok  # real, test-backed fix WITH a captured green run
    reward = (1.0 if passes else 0.0) * (0.9 ** max(0, lines)) * (0.0 if test_changed else 1.0)
    # fix_rerun is the after-fix proof that ships in the PR — it is ONLY the captured green run, never the
    # model's free-text `rerun` arg (paraphrased/fabricated traces in PRs are forbidden, P17).
    sol = Solution(id=len(_SOLUTIONS), bug_id=bug.id, fixed=fixed, fix_diff=diff[:2000],
                   fix_rerun=fix_trace[:3500], lines_changed=lines,
                   test_changed=test_changed, reward=round(reward, 4))
    _SOLUTIONS.append(sol)
    return sol


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
    a = ans.strip()
    low = a.lower()
    # A distinctness signal (or NEW) means DO NOT merge — this is the safe direction (a false merge DROPS a
    # real bug; a missed merge only wastes reproduce budget). This catches the false-merge case the old
    # first-\d+ parse fell for ("distinct, but relates to line 7").
    if "new" in low or any(w in low for w in ("distinct", "unrelated", "different", "none", "not a", "no dup")):
        return None
    # Otherwise accept a TERSE id reference — a real (slightly non-compliant) LLM says "3" / "#3" / "id 3" /
    # "same as #3" / "duplicate of 3" / "3.". Bounded length keeps it to a merge answer, not a long prose
    # explanation that merely happens to contain a number.
    m = re.search(r"#?\s*(\d+)", a)
    if m and len(a) <= 60:
        i = int(m.group(1))
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

# AUTHORITATIVE run log: every run_java is appended here (the GENUINE tool output, never the model's prose).
# The reproducer's bug_trace (the failing run that demonstrates the bug) and the solver's fix_rerun (the
# passing run that demonstrates the fix) are read from THIS, not self-reported — so a trace can't be faked.
_RUNS = []      # [{"cmd","version","rc","out"}] for the agent currently running; reset per reproduce/solve


# A verbose Maven build buries the test result (Tests run / BUILD line) at the END of a long log, after
# pages of plugin setup (bnd, central-publishing, jacoco...). A raw dump that is later FRONT-truncated for
# storage loses exactly the lines that matter. So CONDENSE at record time: keep only the test-runner lines,
# pulled from anywhere in the full output, before any truncation. The result is short, meaningful, and
# survives storage caps. _trace_shows_fail/pass then read this condensed form (the summary lines are kept).
# Keep the test-runner lines across all three runners we see: Maven/surefire (`Tests run: …`, `<<< FAILURE`,
# `BUILD SUCCESS/FAILURE`), Gradle (`> Task :…test`, `BUILD SUCCESSFUL/FAILED`, `N tests completed, M failed`),
# and the raw JUnit console runner (`OK (N tests)`, and `Tests run: N, Failures: N` on failure).
_TRACE_KEEP = re.compile(
    r"Running [\w.]+"
    r"|Tests run:"
    r"|<<< (FAILURE|ERROR)"
    r"|BUILD (SUCCESS|FAILURE|SUCCESSFUL|FAILED)"
    r"|> Task :[\w:.-]*test|\d+ tests? completed|OK \(\d+ tests?\)"
    r"|Expecting |expected[:<]|but was|AssertionError|[A-Za-z][\w.]*Exception"
    r"|^\s+at [\w.$]+\([^)]*:\d+\)"
    r"|No tests (to run|matching)|There (was|were) .*failure")


def _condense(cmd, out):
    keep = [ln.rstrip() for ln in str(out or "").splitlines() if _TRACE_KEEP.search(ln)]
    body = "\n".join(keep[-25:]) if keep else str(out or "")[-1000:]
    return (f"$ {cmd}\n{body}").strip()


def _record_run(cmd, version, rc, out):
    _RUNS.append({"cmd": str(cmd), "version": str(version), "rc": int(rc),
                  "trace": _condense(cmd, out)})


def _trace_shows_fail(r):
    """A genuine FAILING test run across Maven / Gradle / JUnitCore: a non-zero failure/error COUNT (the bug
    manifesting). A setup BUILD FAILURE (no tests matched, nothing compiled) is NOT a reproduction and must be
    rejected — `mvn test -Dtest=X` finding nothing would falsely 'confirm' a bug (seen on synthbench/verbose)."""
    s = r.get("trace", "")
    if re.search(r"No tests (to run|matching|were executed)|were no tests", s):
        return False
    return bool(re.search(r"(Failures|Errors):\s*[1-9]", s)                       # surefire / JUnitCore
                or re.search(r"Tests run:\s*\d+,\s*Failures:\s*[1-9]", s)
                or re.search(r"\d+ tests? completed,\s*[1-9]\d* failed", s)        # gradle (with counts)
                # Gradle often prints a failing run WITHOUT a surefire-style count line — only the failed
                # test TASK and the literal "There were failing tests" notice. Match those, but NEVER a
                # compile task failure (:compileJava/:compileTestJava FAILED is a SETUP error, not the bug
                # manifesting), and use the EXACT Gradle phrase — a broad `.*fail(ing|ure)` matched benign
                # "There were no failures." and non-test plugin failures (spotbugs/enforcer) as test fails.
                or re.search(r"> Task :(?!compile)[\w:.-]*[Tt]est\w*\s+FAILED", s)
                or "There were failing tests" in s)


def _trace_shows_pass(r):
    """A genuine PASSING test run across Maven / Gradle / JUnitCore: a test actually ran and is green."""
    s = r.get("trace", "")
    rc0 = r.get("rc", 0) == 0
    maven = bool(re.search(r"Tests run:\s*[1-9]\d*,\s*Failures:\s*0,\s*Errors:\s*0", s)) and ("BUILD SUCCESS" in s or rc0)
    # Gradle: BUILD SUCCESSFUL is necessary but not sufficient — a cached `> Task :test UP-TO-DATE` (or
    # NO-SOURCE / SKIPPED) means NO test ran, so it must not count as a passing test run. Require a test
    # EXECUTION task with no cached/skipped suffix, or an explicit "N tests completed" (and no failures).
    gradle_ran = any(
        re.search(r"> Task :(?!compile)[\w:.-]*[Tt]est\w*\b", ln)
        and not re.search(r"UP-TO-DATE|NO-SOURCE|SKIPPED|FROM-CACHE", ln)
        for ln in s.splitlines())
    gradle = (("BUILD SUCCESSFUL" in s)
              and (gradle_ran or bool(re.search(r"\d+ tests? completed", s)))
              and not re.search(r"\d+ tests? completed,\s*[1-9]", s))
    junitcore = bool(re.search(r"\bOK \(\d+ tests?\)", s)) and rc0
    return bool(maven or gradle or junitcore)


def _selector(test_cmd, test_path=""):
    """The simple test-class token identifying the bug's OWN test (e.g. 'FooBugTest'), parsed from the test
    command (-Dtest=… / --tests …) or, failing that, the test file's basename. Used to BIND the captured
    before/after traces to this one test — a green/red run of some OTHER test must not become the proof."""
    cmd = str(test_cmd or "")
    m = re.search(r"-D(?:it\.)?test=([^\s]+)", cmd) or re.search(r"--tests[=\s]+[\"']?([^\s\"']+)", cmd)
    tok = (m.group(1) if m else "").strip("\"'")   # drop surrounding quotes (e.g. -Dtest='Outer$Nested')
    tok = re.split(r"[#,(]", tok)[0]               # drop #method / a,b / params
    tok = tok.rsplit(".", 1)[-1].strip("*")        # simple class name, drop package + globs
    if not tok and test_path:
        tok = os.path.basename(str(test_path)).rsplit(".", 1)[0]
    return tok


def _run_matches(r, sel):
    """True if run `r` exercised the selected test. The selector must appear as a WHOLE identifier token in
    the command or condensed trace (bounded by non-word chars), not as a naive substring — else a
    pathological-but-legal class name like `Test` (substring of 'Tests run:') or `C` (of 'BUILD SUCCESSFUL')
    would match every run and re-open the unbound-proof hole. Empty selector = unbound (no test identity)."""
    if not sel:
        return True
    pat = re.compile(r"(?:^|[^\w])" + re.escape(sel) + r"(?![\w])")
    return bool(pat.search(str(r.get("cmd", "")))) or bool(pat.search(str(r.get("trace", ""))))


def _last_fail_trace(sel=""):
    for r in reversed(_RUNS):
        if _run_matches(r, sel) and _trace_shows_fail(r):
            return r["trace"]
    return ""


def _last_pass_trace(sel=""):
    for r in reversed(_RUNS):
        if _run_matches(r, sel) and _trace_shows_pass(r):
            return r["trace"]
    return ""


def _reset_verdict():
    _VERDICT.clear()
    _RUNS.clear()


_FIX = {}   # the solver writes its fix here via the record_fix tool


def _reset_fix():
    _FIX.clear()
    _RUNS.clear()


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
    repro_kind: str = Field(description="regression_test | test | log | grep. To CONFIRM a bug you MUST have a "
                            "unit test that FAILS on it — regression_test (a @Test you wrote via create_test or "
                            "into an existing *Test.java) or test (an existing test that now fails). log/grep "
                            "show nothing manifesting, so they can ONLY support a refuted verdict (a right log, "
                            "or a grep proving the suspected code isn't there) — never a confirm.")
    test_path: str = Field(default="", description="for a confirm: the path of the failing test file (e.g. "
                           "foo/src/test/java/.../BarBugTest.java).")
    test_src: str = Field(default="", description="for a confirm: the test source (the @Test or full class). The "
                          "harness ALSO reads the real file from disk via test_path, so make test_path exactly "
                          "right — that on-disk file is what ships, what the fix step re-runs, and what the gate "
                          "re-runs on /src/old.")
    test_cmd: str = Field(default="", description="for a confirm: the exact run_java command that runs JUST this "
                          "test (e.g. 'mvn -q test -Dtest=BarBugTest -pl modules/core'). The gate re-runs it on "
                          "/src/new (must fail) and /src/old (should pass) — the flip that proves the test is real.")
    build_edit_path: str = Field(default="", description="if you edited a build file to add a TEST-scope dep "
                          "(e.g. mockito-core) the test needs, its path (e.g. pom.xml or modules/core/pom.xml). "
                          "Empty if you added no dependency.")
    build_edit_src: str = Field(default="", description="if build_edit_path is set: the FULL new content of that "
                          "build file — captured so the fix step (and the PR) keep the test compilable.")
    reproduction: str = Field(description="The actual RUN: the command(s) you executed and their real output — "
                       "the failing test, the compile error, the log value, or the empty grep. The output, not "
                       "a description of it.")
    evidence: str = Field(description="One-line summary: file:line + what the run showed.")


class RecordVerdictObservation(Observation):
    pass


_VERDICT_DESC = ("Record your decision on the one suspicion, ONCE, LAST. A bug is CONFIRMED only by a unit "
                 "test that FAILS on it (repro_kind=regression_test|test, with test_path + test_src + "
                 "test_cmd) — a grep/log shows nothing manifesting and can only support REFUTED (a right log, "
                 "or a grep proving the code isn't there). No failing test → not a confirm. Reading and "
                 "concluding settles nothing. The confirm then passes a gate (re-run on /src/old for the flip, "
                 "+ a critic) before it becomes a bug. Args: verdict, repro_kind, test_path + test_src + "
                 "test_cmd (confirm), reproduction (command(s) run + real output), evidence.")


class _RecordVerdictExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _VERDICT["verdict"] = str(action.verdict).lower().strip()
        _VERDICT["repro_kind"] = str(action.repro_kind).lower().strip()
        _VERDICT["test_path"] = str(getattr(action, "test_path", ""))
        _VERDICT["test_src"] = str(getattr(action, "test_src", ""))
        _VERDICT["build_edit_path"] = str(getattr(action, "build_edit_path", ""))
        _VERDICT["build_edit_src"] = str(getattr(action, "build_edit_src", ""))
        _VERDICT["test_cmd"] = str(getattr(action, "test_cmd", ""))
        _VERDICT["reproduction"] = str(action.reproduction)
        _VERDICT["evidence"] = str(action.evidence)
        # AUTHORITATIVE capture: read the test (and build) file from the worktree as it stands NOW — the model
        # just compiled and ran it, so disk holds the REAL, complete file. This overrides whatever the model
        # pasted, which is often only the injected @Test snippet (writing that as the whole file later
        # corrupts it — missing package/imports/class). Disk is the truth; the pasted args are a fallback.
        _disk_test = _read_worktree_file(_VERDICT["test_path"])
        if _disk_test:
            _VERDICT["test_src"] = _disk_test
        _disk_build = _read_worktree_file(_VERDICT["build_edit_path"])
        if _disk_build:
            _VERDICT["build_edit_src"] = _disk_build
        # FULL test scaffolding: a test rarely lives in one file — it often needs a helper stub/mock edited
        # (e.g. HikariCP's StubConnection.schemaTransform) or a test resource. Capture EVERY dirty file under
        # any src/test tree, not just the named test, so the solver can re-materialize all of it into a clean
        # worktree and the test compiles. Without this the solver is forced to patch scaffolding -> test_changed.
        _VERDICT["test_files"] = {p: c for p, c in _sandbox.dirty_files("new").items()
                                  if "/src/test/" in ("/" + p.replace("\\", "/"))}
        # symmetric guard: NEITHER verdict counts without a real run. No run -> inconclusive.
        if _VERDICT["repro_kind"] not in ("regression_test", "test", "log", "grep"):
            _VERDICT["verdict"] = "inconclusive"
            return RecordVerdictObservation.from_text(
                text="a verdict has to be SHOWN by a run. Inconclusive — run something and record again.")
        # bug_trace: the AUTHORITATIVE failing run captured from run_java (the bug manifesting), not the model's
        # prose. This is the proof that ships in the PR; it is read off the genuine tool output, never typed —
        # and BOUND to this suspicion's own test (selector), so an unrelated failing run can't satisfy the gate.
        _VERDICT["bug_trace"] = _last_fail_trace(_selector(_VERDICT["test_cmd"], _VERDICT["test_path"]))
        # CONFIRM requires a failing unit test that ACTUALLY went red in a run. grep/log can only refute (they
        # show nothing manifesting); a confirm without a real failing test (test_src) AND a captured failing
        # trace (_last_fail_trace) is not a bug — the reproducer earns nothing for it.
        if _VERDICT["verdict"] == "confirmed" and (
                _VERDICT["repro_kind"] not in ("regression_test", "test")
                or not _VERDICT["test_src"].strip() or not _VERDICT["bug_trace"]):
            _VERDICT["verdict"] = "inconclusive"
            return RecordVerdictObservation.from_text(
                text="a bug is CONFIRMED only by a unit test that FAILS on it — write a @Test that goes red on "
                     "the bug and run_java it so the failure is captured (test_path + test_src + test_cmd), then "
                     "record again. No captured failing run (Tests run … Failures: >0) → inconclusive, not a "
                     "confirm. A grep/log can only support 'refuted'.")
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
        # AUTHORITATIVE pass trace: the genuine green run captured from run_java (overrides the self-reported
        # rerun). The solver's reward is gated on this, so "fixed" can't be claimed without a real green run.
        _FIX["fix_trace"] = _last_pass_trace()
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
# run_java must be ONE invocation of an allowed program. exec_ pipes the WHOLE string to `bash -s`, so any
# statement separator lets a SECOND program run and overwrite the class-under-test with a stub (no_cheat
# fully bypassed). A denylist of separators is whack-a-mole — the original blocked ; && || | but missed a
# bare newline, and then `&` (background), `(` (subshell), `$(`/backtick (substitution), and exotic unicode
# line separators. So reject STRUCTURALLY: no shell metacharacter, and no whitespace other than space/tab
# (every other whitespace char — \n \r \v \f NEL LS PS … — is a statement separator). With no separator a
# second program cannot be expressed at all, so cp/mv/rm/sed/truncate/install can never overwrite the class.
# `$` is deliberately NOT here: a JUnit5 @Nested selector is `-Dtest='Outer$Nested'`, and the dangerous
# substitution forms `$(` and `${` are ALREADY blocked by the `(` and `{` rules, so a bare `$` (a quoted
# nested-class name, or a $VAR that can only expand to a value — the agent can't set env vars) is safe.
_RUNJAVA_META = re.compile(r"[;&|<>(){}`\\]")


def _runjava_reject(cmd):
    """Reason a run_java command is refused, or None if it's a single allowed invocation. Shared by the
    run_java executor AND the flip gate, so neither can be handed a multi-statement command."""
    s = str(cmd)
    toks = s.split()
    first = toks[0] if toks else ""
    if first not in _RUNJAVA_OK:
        return ("run_java only runs mvn/gradle/java/javac with no shell redirection or file-writing. "
                "To change code use edit_file (existing files only).")
    if any(ch.isspace() and ch not in (" ", "\t") for ch in s):
        return ("run_java runs ONE command on ONE line — no newlines or other whitespace separators. "
                "To change code use edit_file (existing files only).")
    if _RUNJAVA_META.search(s):
        return ("run_java runs ONE build/run command — no shell separators (; & |), redirection (< >), "
                "subshells (), substitution ($ `), or file-writing. To change code use edit_file.")
    return None


class _RunJavaExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        cmd = str(action.command).strip()
        reason = _runjava_reject(cmd)
        if reason:
            return RunJavaObservation.from_text(text="rejected: " + reason)
        ver = getattr(action, "version", "new")
        # Strip -q/--quiet: a QUIET passing test prints no surefire summary (`Tests run … Failures: 0`) and no
        # `BUILD SUCCESS` (both INFO-level), so a genuine green run can't be recognised and the fix scores 0
        # by the trace gate. Failures print at ERROR even under -q (so bug_trace survived), but the pass does
        # not — strip it so every run emits a recognisable summary. Output-only flag; safe to drop.
        cmd = " ".join(t for t in cmd.split() if t not in ("-q", "--quiet", "-quiet"))
        rc, out = _sandbox.exec_(cmd, version=ver)
        _record_run(cmd, ver, rc, out)   # authoritative trace capture (bug_trace / fix_rerun read from here)
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
    # NORMALIZE first: a raw string like "mod/src/test/../../src/main/x/FooTest.java" textually contains
    # /src/test/ but resolves into src/main — create_test validates this predicate on the raw rel yet writes
    # at the normalized path, so without normalizing here a *Test.java could land outside a src/test tree.
    rel = os.path.normpath(str(rel).replace("\\", "/")).replace("\\", "/")
    base = rel.rsplit("/", 1)[-1]
    return ("/src/test/" in ("/" + rel)) and base.endswith(("Test.java", "Tests.java", "IT.java"))


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
        # NORMALIZE before the src/test check: the raw-string check missed a traversal like
        # 'mod/src/main/../test/java/x/FooBugTest.java' (no literal '/src/test/' substring) which
        # _EditFileExecutor then normalizes back INTO src/test and edits — letting the solver weaken the
        # very test that grades it. Normalize so the guard sees the real destination.
        norm = os.path.normpath(str(getattr(action, "path", "")).replace("\\", "/")).replace("\\", "/")
        if "/src/test/" in ("/" + norm):
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

CRUCIAL — what your @Test ASSERTS must be the GENUINELY-CORRECT behaviour, not a convenient one. You author
both the test and (later) the fix, so a green test only proves they AGREE with each other, NOT that the
expectation is right. Before you assert, REASON about the correct behaviour from authority: the type/library
SPEC (Javadoc, the JLS), the serialization/round-trip contract (a value the code WRITES must read back), and
how SIBLING code handles the same case. Example: gson serialises `Locale.ROOT` to `""`, so deserialising `""`
must round-trip to `Locale.ROOT` — asserting that it THROWS encodes the wrong spec, and the resulting "fix"
is wrong-but-green. If the right behaviour is genuinely a judgment call, take the spec/round-trip answer.

Real code is coupled — the method you want to hit pulls in clients, services, or I/O — and that is what
MOCKING is for, not a reason to retreat to grep. Mock the COLLABORATORS (never the class under test) to
isolate it AND to drive the path you need: make a mocked dependency throw so a catch block runs, or return a
crafted value to reach a branch. Mockito is the tool — `mock(Dep.class)` + `when(dep.f()).thenThrow(...)`;
for statics like `System.exit`, `mockStatic(System.class)` (needs mockito-inline / Mockito 5+), or
`system-lambda`'s `catchSystemExit(...)`, or a `SecurityManager` whose `checkExit` throws (JDK-only, no
dependency). Check the pom/build for mockito-core / mockito-inline / system-lambda first; if Mockito is NOT
present, you MAY add it yourself — `edit_file` the pom.xml (or build.gradle) to add `org.mockito:mockito-core`
at TEST scope (a recent 5.x has static mocking built in: `testImplementation`/`<scope>test</scope>`). Adding
a test-scoped test library is normal PR work and allowed; only ever touch TEST scope, never a production
dependency. The rule: never mock the class or the method whose bug you're proving — the assertion has to run
the REAL buggy code. A bug that "needs real infrastructure" almost always just needs its collaborators mocked.

Your tools are deliberately narrow: read tools to navigate; `edit_file` (modify an EXISTING file — add a
@Test or a log line); `create_test` (a NEW test under src/test/ only); `run_java` (mvn/./mvnw/gradle/./gradlew/
java/javac only — no shell, no redirection). You cannot write production code, so a copy/stub/standalone
driver isn't possible — you exercise the real class or you have nothing.

Your score:
    reward = no_cheat · ran · shown
             · 0.9^(mock_loc / covered_loc) · 0.9^(test_loc) · 0.9^(reflection_ops) · 0.9^(inner_classes_loc)
           + extra_bugs_found

  no_cheat = 1 because you can only touch the real code + a real test (the tools allow nothing else); 0 if
           you settle a verdict without a run.
  ran    = 1 if you got the genuine project classes (and your test) to compile and run — not a sketch.
  shown  = 1 ONLY if your unit test FAILS on the bug AND survives the gate (below); a log or grep shows
           nothing manifesting — it supports a REFUTE, never a confirm, and earns shown=0. The three gates
           MULTIPLY: no flipping test → no confirm → no reward, however clean. The failing run itself is the
           proof: the LAST run_java where the test goes red (`Tests run … Failures: >0`) is captured verbatim
           as the bug's `bug_trace` (the fail-before evidence that ships in the PR) — so you must actually
           run_java the test and SEE it red; a confirm with no captured red run is downgraded to inconclusive.
  The 0.9^ factors then discount HOW the proof is written — they only bite once shown=1, and a tiny lambda
  test driving the real class keeps every one near 1 (the same 0.9 lever as the solver's 0.9^lines):
    0.9^(test_loc)             — the smaller the test, the better; every line you don't write is reward.
    0.9^(mock_loc/covered_loc) — exercise REAL code: the more of what the test runs is mock setup vs the
                                 production lines it covers, the more it decays. Mock collaborators, not bulk.
    0.9^(reflection_ops)       — reach the bug through the PUBLIC API; each setAccessible/getDeclared* op
                                 decays it (reflect only when no public path reaches the behaviour).
    0.9^(inner_classes_loc)    — prefer a lambda; lines inside an anonymous inner class decay it (and they
                                 count in test_loc too, so the lambda wins twice).
  extra_bugs_found = a different real bug you notice while in the code and raise with add_suspicion that
           later confirms — it pays on TOP, undiscounted (it earns its own clean score when itself reproduced).

The gate (every confirm passes it before it becomes a bug): your test is re-run on BOTH trees — a genuine
regression FAILS on /src/new and PASSES on /src/old (so give an accurate `test_cmd` that runs just your
test); if it can't flip (e.g. a pre-existing bug failing on both), a critic agent checks the test actually
demonstrates the suspicion. `assert(false)` and tests that fail on a compile/setup error are rejected — they
earn nothing. So make the test genuinely exercise the suspected behaviour.

The loop: write the failing @Test (edit_file into an existing *Test.java, or create_test for a new one) →
run_java it → watch it go red → record. A different real bug you notice along the way pays too — raise it
with add_suspicion. reset_workspace anytime. Record with record_verdict(verdict, repro_kind=regression_test|
test for a confirm — grep/log only refute, test_path + test_src + test_cmd, reproduction = the commands you
ran + their output, evidence)."""

SOLVER_SYS = """A unit test was written that fails because of one real bug. Your job: make the production code
do the CORRECT thing — which makes that test pass as a side effect, not the other way round.

First, reason about what the correct behaviour SHOULD be, from authority — the type/library SPEC (Javadoc, the
JLS), the serialization/round-trip contract (a value the code WRITES must read back identically), and how
SIBLING code handles the same case. A passing test is NOT proof of correctness: the same pipeline wrote both
the test and (now) the fix, so making it green only proves they agree — it can agree on the WRONG behaviour.
If the test's expectation actually contradicts the spec (e.g. it asserts a throw where the round-trip says the
value should map back to a canonical default), do NOT force a wrong-but-green fix — record fixed=false and say
the test encodes the wrong expectation. Pick the canonical answer (e.g. `Locale.ROOT`, not `new Locale("")`).

You have `edit_code` to change existing PRODUCTION source (it refuses src/test, so you cannot weaken the
test that grades you) and `run_java` to re-run the test (mvn/./mvnw/gradle/./gradlew/java/javac — no shell).
Work the natural loop: edit the code, run the test, read the output, repeat until it is green.

Two things shape your score:
    reward = passes · 0.9^(lines_changed) · test_untouched

  passes         — the test now passes and nothing else breaks. Show it by re-running, not by asserting: the
                   LAST run_java where the test is green (`Tests run … Failures: 0, Errors: 0` + BUILD SUCCESS)
                   is captured verbatim as the `fix_rerun` (the after-fix proof that ships in the PR), and the
                   reward is GATED on it — `fixed=true` with no captured green run scores 0.
  0.9^lines      — the fewer production lines you change, the better (0 lines = 1.0, 5 ≈ 0.59, 10 ≈ 0.35), so
                   look for the tight, root-cause fix rather than a broad rewrite.
  test_untouched — 1 if you leave the test exactly as written, 0 if you change even a single line of it.
                   Changing the test to make it pass isn't a fix, so a touched test scores nothing. You can
                   edit it, but please don't — fix the code instead.

So: the smallest real production change that turns the test green, with the test left alone. Record with
record_fix(fixed, fix_diff = your change, rerun = the test output that shows it passing). If you can't,
fixed=false — that's fine, leave it for the author."""

SYNTHESIZER_SYS = """You write the final Java code review from CONFIRMED findings only — each one a bug the
reproducer showed in the real code, some with a fix the solver verified. Turn each into a point with its
file:line, what the bug is, and the fix if there is one. Add no new claims of your own. A short, sharp
review beats a flood. Output SUMMARY: then POINTS:, each as - [path/File.java:line] <bug> [— fix: <fix>]."""


# --- registry entry types: suspicion -> bug -> solution ---------------------------------------------
@dataclass
class Suspicion:
    """Stage 1 — the investigator's hypothesis. Confidence is the only priority signal."""
    id: int
    observation: str                  # what the investigator literally saw
    suspected_bug: str                # the bug it might cause (hypothesis)
    location: str
    confidence: float
    status: str = "pending"           # pending / proven / refuted / inconclusive (proven => a Bug exists)


@dataclass
class Bug:
    """Stage 2 — a suspicion PROVEN by a failing unit test that passed the gate (flip / critic)."""
    id: int
    suspicion_id: int                 # the Suspicion this was promoted from
    observation: str
    suspected_bug: str
    location: str
    repro_kind: str = ""              # regression_test / test — confirmed only by a failing unit test
    evidence: str = ""                # one-line: file:line + what the run showed
    reproduction: str = ""            # the actual run: command(s) + output proving it fails
    bug_trace: str = ""               # AUTHORITATIVE failing run captured from run_java (the bug manifesting,
    #                                   `Tests run … Failures: >0`) — the fail-before proof pasted into the PR
    test_path: str = ""               # the unit/regression test file (ships in the PR)
    test_src: str = ""                # full test source captured from disk (fail-before / pass-after)
    test_cmd: str = ""                # the command that runs just this test (gate re-runs it on both trees)
    validation: str = ""             # how the gate cleared it: "flip" or "critic …"
    build_edit_path: str = ""         # build file edited to add a test-scope dep (e.g. mockito), if any
    build_edit_src: str = ""          # full new content of that build file (re-applied for the solver + PR)
    test_files: dict = field(default_factory=dict)  # FULL test scaffolding {path: content} the reproducer
    #                                                  wrote under src/test (helper stubs/mocks/resources +
    #                                                  the named test) — re-materialized so the test compiles


@dataclass
class Solution:
    """Stage 3 — the solver's verified fix for a Bug."""
    id: int
    bug_id: int                       # the Bug this fixes
    fixed: bool = False               # the regression test now passes, nothing else broken
    fix_diff: str = ""                # the production-code change
    fix_rerun: str = ""              # rerun output proving the test is green
    lines_changed: int = 0            # MEASURED production lines the patch touches (git, excl. test + dep)
    test_changed: bool = False        # solver edited the test itself (any line) -> reward 0
    reward: float = 0.0               # passes · 0.9^lines_changed · (test_changed ? 0 : 1)


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
                       ("create_test", CreateTestTool), ("edit_code", EditCodeTool), ("repo_map", RepoMapTool),
                       ("record_judgment", RecordJudgmentTool)):
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


_STALL_LIMIT = int(os.environ.get("OH_STALL_LIMIT", "8"))   # consecutive empty-response nudges -> abort


def _msg_text(ev):
    """Concatenated text of a MessageEvent's content blocks (for spotting the corrective nudge)."""
    m = getattr(ev, "llm_message", None)
    try:
        return " ".join(getattr(c, "text", "") or "" for c in (getattr(m, "content", None) or []))
    except Exception:  # noqa: BLE001
        return str(m or "")


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
    # Stall guard: the model can fall into a degenerate loop where it returns NO tool call and NO content,
    # and OpenHands answers each with a "please use a tool" nudge forever (the gson hang). This is NOT
    # productive depth — it makes zero progress. Count CONSECUTIVE nudges (any real ActionEvent resets it)
    # and pause the run once it's clearly stuck. Progress-based, not a wall-clock/step cap: deep work that
    # keeps acting never trips it. (A truly hung socket emits no events at all — that's keepalive + the
    # byte-gap request_timeout's job, P8; this catches the live-but-looping case.)
    _stall = {"n": 0, "conv": None}

    def _stall_guard(ev):
        try:
            if isinstance(ev, ActionEvent):
                _stall["n"] = 0
            elif (isinstance(ev, MessageEvent) and getattr(ev, "source", "") == "user"
                    and "did not include a function call" in _msg_text(ev)):
                _stall["n"] += 1
                if _stall["n"] >= _STALL_LIMIT and _stall["conv"] is not None:
                    print(f"  [stall] {_STALL_LIMIT} consecutive empty responses — pausing the agent", flush=True)
                    try:
                        _stall["conv"].pause()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    conv = Conversation(agent=agent, workspace=ws, visualizer=harness._DialogViz,
                        persistence_dir=None, callbacks=[_stall_guard])
    _stall["conv"] = conv
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
    """Pull any store entries not yet tracked into by_id as pending Suspicion objects, AND propagate a dedup
    confidence bump onto an already-tracked entry. A confident re-sighting during reproduction bumps
    _STORE[id]["confidence"], but that bump used to live only in _STORE — it never reached the scheduler
    (which reads Suspicion.confidence) or the registry JSON, so a surer re-sighting could not raise priority.
    Re-sync here, max-only (never lower a confidence)."""
    for d in _STORE:
        if d["id"] not in by_id:
            try:
                by_id[d["id"]] = Suspicion(id=d["id"], observation=d["observation"],
                                           suspected_bug=d["suspected_bug"], location=d["location"],
                                           confidence=float(d["confidence"]))
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                by_id[d["id"]].confidence = max(by_id[d["id"]].confidence, float(d["confidence"]))
            except Exception:  # noqa: BLE001
                pass


INVESTIGATE_FILE_SYS = """You investigate a Java repository for real bugs, starting from ONE entrance file.
Real reviewers find bugs everywhere, and every confirmable bug you surface is valuable.

Your score:
    reward = Σ confidence(s) over your suspicions that get CONFIRMED

Only confirmed bugs pay, each weighted by the confidence you staked on it — a refuted or un-confirmable guess
scores 0, so flag generously: a bug you miss is gone for good, an extra guess is free. Put high confidence on
what you genuinely believe, lower on the long shots; honest confidence is also what gets the surest ones
reproduced first. (You do NOT have to read the whole repo or worry about coverage — coverage is handled for
you: a separate investigator enters from EVERY other file. Your job is just YOUR entrance and its neighbours.)

You are handed ONE entrance file. READ IT IN FULL with file_editor, then explore OUTWARD from it as the code
leads you — the classes it calls, its callers, a sibling that shares the pattern — using search/grep/glob. Do
not wander the whole tree; cover your entrance and its immediate neighbourhood well. The moment you SEE
something off — a contract violation, a copy-paste slip, a wrong comparison/operator, an off-by-one, a
resource leak, a mishandled edge case — record it with add_suspicion (observation + suspected_bug + location +
confidence). Do not verify it yourself; the reproducer will. Do not flag style, naming, or pure speculation —
only concrete things you actually saw in the code. Bias to bugs the tests can exercise — those are bankable."""


def _source_files(root, cap=8000):
    """Every MAIN-source .java file — the entrance points, one investigator each. Excludes tests, generated
    code, and build output (not where a shippable, ownable bug lives). Falls back to all non-test .java if a
    repo doesn't use the src/main/java layout, so no repo yields an empty worklist."""
    skip = {".git", "target", "build", "out", "bin", "node_modules", ".idea", ".gradle"}
    main, other = [], []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in skip]
        norm = dp.replace("\\", "/") + "/"
        if "/src/test/" in norm or "/test/" in norm or "generated" in norm:
            continue
        for fn in fns:
            if not fn.endswith(".java"):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), root)
            (main if "/src/main/java/" in norm else other).append(rel)
    return sorted(main or other)[:cap]


def investigate_file(repo_dir, entry_file):
    """One investigator seeded at ONE entrance file: reads it in full and explores outward, flagging bugs."""
    _run_agent(INVESTIGATE_FILE_SYS,
               f"Your entrance file is:\n    {entry_file}\n\nOpen it in full with file_editor, then explore "
               "outward from it as the code leads you, and record each suspicion with add_suspicion.",
               repo_dir, base=("search", "grep", "glob", "file_editor"), extra_tools=[CAPTURE])


def investigate_repo(repo_dir):
    """Whole-repo investigator, BY FILE: one investigator per source file (its entrance point), all writing the
    shared suspicion store. Coverage of the repo is STRUCTURAL — every file is handed out, so there is no
    coverage reward term; the per-file reward is just confirmed bugs. This is the fan-out that actually reads
    every file (one agent's context window can't), at the cost of one investigator run per source file."""
    files = _source_files(repo_dir)
    print(f"  [investigate] {len(files)} source files -> one investigator per file (entrance points)", flush=True)
    for i, rel in enumerate(files, 1):
        print(f"  [file {i}/{len(files)}] {rel}", flush=True)
        investigate_file(repo_dir, rel)


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
           "watch it go red on /src/new and (ideally) green on /src/old. A failing test is the ONLY way to "
           "confirm — a log or grep can only REFUTE. If the code is coupled (needs a client, service, or I/O) "
           "or the path is an exception/exit, MOCK the collaborators — that's the path: Mockito "
           "`mock(Dep.class)` + `when(...).thenThrow(...)` to drive the catch, `mockStatic(System.class)` / "
           "`catchSystemExit` / a `SecurityManager` for System.exit. If Mockito isn't on the test classpath, "
           "you MAY add `org.mockito:mockito-core` at TEST scope to the pom/build with `edit_file`. Mock the "
           "dependencies, never the class under test. Your confirm then passes a gate: the test is re-run on "
           "/src/old (real regression = red on new, green on old) and a critic checks it demonstrates the bug "
           "— so it must genuinely exercise the suspected behaviour (no assert(false)). If you've only read "
           "it, you don't have an answer. Record any NEW bug with add_suspicion. When done, call "
           "`record_verdict` (verdict, repro_kind=regression_test|test to confirm — grep/log only refute, "
           "test_path + test_src + test_cmd = the command that runs just your test, reproduction, evidence).")
    out = _run_agent(REPRODUCER_SYS, msg, repo_dir, base=_READONLY_BASE,
                     extra_tools=[CAPTURE, "run_java", "edit_file", "create_test", "record_verdict",
                                  "reset_workspace"])
    if _VERDICT.get("verdict") in ("confirmed", "refuted", "inconclusive"):   # tool-captured: robust
        return dict(_VERDICT)
    print(f"  [verdict] no record_verdict for S[{s.id}] — inconclusive (nothing run)", flush=True)
    return {"verdict": "inconclusive", "evidence": (out or "")[-300:], "repro_kind": "none"}


def _read_worktree_file(rel):
    """Read a file from the POST-PR worktree by repo-relative path, or '' if missing/escaping. Used to
    capture the actual test/build file at record_verdict time (disk is authoritative over pasted args)."""
    root = _sandbox.workdir("new")
    if not (root and str(rel).strip()):
        return ""
    p = os.path.normpath(os.path.join(root, str(rel)))
    if not p.startswith(os.path.normpath(root) + os.sep) or not os.path.isfile(p):
        return ""
    try:
        return open(p, errors="ignore").read()
    except Exception:  # noqa: BLE001
        return ""


def _scaffold_of(test_files, test_path, test_src):
    """The full set of test-tree files to restore: {path: content}. Prefer captured `test_files` (named test +
    helper stubs/mocks/resources); always include the primary named test (fallback for older entries recorded
    before scaffolding capture)."""
    files = {p: c for p, c in (test_files or {}).items()
             if "/src/test/" in ("/" + str(p).replace("\\", "/"))}
    if str(test_src).strip() and str(test_path).strip() and _is_test_path(test_path):
        files.setdefault(test_path, test_src)
    return files


def _write_scaffold(root, files):
    """Write {path: content} into `root`, skipping any path escaping it. Returns count written."""
    n = 0
    for rel, content in files.items():
        p = os.path.normpath(os.path.join(root, rel))
        if not p.startswith(os.path.normpath(root) + os.sep):
            continue
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(content)
            n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def _test_scaffold(s):
    """The full test-tree file set for Bug `s` (see _scaffold_of)."""
    return _scaffold_of(getattr(s, "test_files", None), s.test_path, s.test_src)


def _materialize_test(s):
    """Re-write the reproducer's regression test AND its full test scaffolding into the clean worktree so the
    solver can run it. These files are untracked/reverted, so reset_clean() (and the solver's own
    reset_workspace) wipe them; we put them all back from the captured scaffolding — not just the named test,
    but every helper stub/mock/resource it needed, so the test actually compiles. The solver can't author them
    himself (edit_code refuses src/test), so the test stays a fixed yardstick he turns green by fixing
    production code — he can't weaken it. Returns True if at least one file was written."""
    root = _sandbox.workdir("new")
    if not root:
        return False
    return _write_scaffold(root, _test_scaffold(s)) > 0


_BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")


def _write_build_edit(root, build_edit_path, build_edit_src):
    """Overwrite a tracked build file (pom.xml / build.gradle[.kts]) under `root` with captured content (the
    reproducer's test-scope dep edit, e.g. mockito-core). reset_clean() reverts the tracked pom/build,
    dropping the dep; this restores it. Restricted to build files; the target must already exist (we only
    restore a tracked file, never create one). Returns True if written."""
    if not (str(build_edit_src).strip() and str(build_edit_path).strip()):
        return False
    if os.path.basename(str(build_edit_path)) not in _BUILD_FILES:
        return False
    if not root:
        return False
    p = os.path.normpath(os.path.join(root, str(build_edit_path)))
    if not p.startswith(os.path.normpath(root) + os.sep) or not os.path.isfile(p):
        return False
    try:
        with open(p, "w") as f:
            f.write(str(build_edit_src))
        return True
    except Exception:  # noqa: BLE001
        return False


def _materialize_build_edit(s):
    """Re-apply the reproducer's build-file edit into the clean /src/new worktree so the solver's re-run of
    the regression test still compiles (reset_clean reverts the tracked pom/build, dropping the dep)."""
    return _write_build_edit(_sandbox.workdir("new"), s.build_edit_path, s.build_edit_src)


# The solver edits PRODUCTION code only: edit_code is edit_file plus a refusal of any src/test path, so it
# structurally CANNOT weaken the regression test that grades it (plain edit_file would let it, then revert).
_SOLVER_TOOLS = ("run_java", "edit_code", "record_fix")


def solve(repo_dir, bug):
    # Reads a Bug from the registry and writes a Solution. Only runs on a PROVEN bug. Full source edit
    # (unlike the reproducer); graded by re-running the bug's own regression test against its patch. Fresh,
    # lean context — just the bug + how it was shown + the test, not the reproducer's whole exploration.
    _reset_fix()
    _sandbox.reset_clean()   # pristine source — the solver fixes from clean, not the reproducer's logging
    _materialize_test(bug)   # put the bug's regression test back (reset_clean wiped the untracked file)
    _materialize_build_edit(bug)  # re-apply the test-scope dep edit (e.g. mockito) reset_clean reverted
    _sandbox.set_no_new_files(True)   # no_cheat backstop; the tool set below (no shell) is the real guarantee
    test_block = (f"the failing test ({bug.test_path}):\n{bug.test_src}\n\n" if bug.test_src else "")
    msg = (f"BUG TO FIX:\nobservation: {bug.observation}\nsuspected_bug: {bug.suspected_bug}\n"
           f"location: {bug.location}\nhow it was shown ({bug.repro_kind}): {bug.evidence}\nreproduction:\n{bug.reproduction}\n\n"
           f"{test_block}"
           "A unit test fails because of this bug. First decide what the code SHOULD do here (the type/library "
           "spec, the serialization round-trip contract, sibling code) — then fix the production code in /src/new "
           "to do that; the test going green is the side effect, not the goal. Re-run it to confirm, changing "
           "nothing else. Tools: `edit_code` (change existing production source — refuses src/test), `run_java` "
           "(re-run the test). Keep the "
           "change small, and don't edit the test itself — a changed test scores zero. If the test's expectation "
           "actually contradicts the correct behaviour, record fixed=false and say so rather than forcing it. "
           "When the test passes, call record_fix (fixed, fix_diff = your change, rerun = the passing output).")
    # No reset_workspace for the solver — a reset would wipe the materialized test (the thing it must pass).
    out = _run_agent(SOLVER_SYS, msg, repo_dir, base=_READONLY_BASE, extra_tools=list(_SOLVER_TOOLS))
    fix = dict(_FIX) if "fixed" in _FIX else {"fixed": False, "fix_diff": "", "rerun": (out or "")[-300:]}
    # MEASURED reward inputs (not the model's self-report). lines_changed = production lines in the worktree
    # diff, excluding the materialized test (src/test) and the re-applied dep (build_edit_path). test_changed
    # = did the solver edit the test itself, vs the test we materialized (disk != bug.test_src).
    stats = _sandbox.diff_numstat("new")
    fix["lines_changed"] = sum(n for p, n in stats
                               if "/src/test/" not in ("/" + p) and p != bug.build_edit_path)
    # test_changed = the solver touched ANY captured test-tree file (the named test OR a helper stub) vs what
    # we materialized. Since the whole scaffolding is restored, a difference now is the solver weakening it.
    scaffold = _test_scaffold(bug)
    fix["test_changed"] = any(_read_worktree_file(p) != c for p, c in scaffold.items())
    return fix


def synthesize(ctx, bugs, solutions, open_suspicions):
    """The PR writer: reads the registry (bugs + their solutions) and prints the review."""
    sol_by_bug = {sol.bug_id: sol for sol in solutions}
    def _one(bug):
        line = (f"- [{bug.location}] {bug.suspected_bug}\n    observation: {bug.observation}\n"
                f"    proven by ({bug.repro_kind}): {bug.evidence}")
        if bug.test_path:
            line += f"\n    regression test: {bug.test_path}"
        sol = sol_by_bug.get(bug.id)
        if sol and sol.fixed:
            line += f"\n    fix ({sol.lines_changed} lines): {sol.fix_diff[:400]}"
        return line
    body = "PROVEN BUGS (each reproduced in the real code; some with a verified fix):\n" + (
        "\n".join(_one(b) for b in bugs) or "(none)")
    if open_suspicions:
        body += "\n\nOPEN QUESTIONS (couldn't be settled by a run — include as hedged questions):\n" + "\n".join(
            f"- {s.suspected_bug} [{s.location}]" for s in open_suspicions)
    txt = _llm_call(SYNTHESIZER_SYS, "PULL REQUEST (context):\n" + ctx[:8000] + "\n\n" + body +
                    "\n\nWrite the review.")
    return final_review(_post_think(txt))


# --- the gate between reproduce and bug: a failing test must really demonstrate the suspicion -----------
# Two overlapping slices (swiss-cheese): (1) an EXECUTABLE flip — a genuine regression test FAILS on /src/new
# and PASSES on /src/old; assert(false) fails on both, so it can't flip. (2) a CRITIC subagent for the cases
# the flip can't settle (pre-existing bugs that fail on both, or a test that won't compile on /src/old).
TEST_CRITIC_SYS = ("You judge whether a FAILING Java test genuinely demonstrates a specific suspected bug, or "
                   "is a fake/irrelevant pass-the-gate test. REJECT if it is trivial (asserts false / fail() / "
                   "asserts a constant), if it fails on a COMPILE or SETUP error rather than the asserted "
                   "behaviour, or if it exercises something unrelated to the suspicion. APPROVE only if the "
                   "test runs the real class named in the suspicion and fails because of the suspected wrong "
                   "behaviour. Reply ONLY 'APPROVE' or 'REJECT: <one-line reason>'.")


def _flip_check(verdict):
    """Run the reproducer's test on BOTH trees, HERMETICALLY. A real regression FAILS on /src/new and PASSES
    on /src/old. Returns (ran, new_fails, old_passes); ran=False when we can't run it (no test_cmd / bad cmd
    / no worktree). Two guarantees the old version lacked:
      - RESET both trees to pristine PR code first, then re-materialize ONLY the test scaffolding. The
        reproducer is allowed to edit_file production code (to add logging); without a reset the flip would
        run against that contaminated tree, so a FABRICATED regression (production edited to break, test
        asserting the original behaviour) would 'flip' and mint a false bug. Resetting makes the flip run
        against the REAL PR code plus the test alone.
      - judge by _trace_shows_fail / _trace_shows_pass, NOT raw exit codes: a compile failure (exit!=0 with
        no test) or a no-tests-matched run (exit 0) would otherwise read as the bug manifesting / the test
        passing, a vacuous flip."""
    cmd = str(verdict.get("test_cmd", "")).strip()
    tp, ts = str(verdict.get("test_path", "")), str(verdict.get("test_src", ""))
    if not (cmd and tp and ts and _is_test_path(tp)) or _runjava_reject(cmd):
        return (False, False, False)
    root_new, root_old = _sandbox.workdir("new"), _sandbox.workdir("old")
    if not (root_new and root_old):
        return (False, False, False)
    scaffold = _scaffold_of(verdict.get("test_files"), tp, ts)
    be_path, be_src = str(verdict.get("build_edit_path", "")), str(verdict.get("build_edit_src", ""))
    _sandbox.reset_clean()                                   # pristine PR code on BOTH trees (drop any prover edits)
    if _write_scaffold(root_new, scaffold) == 0:            # re-materialize the test the reset just wiped
        return (False, False, False)
    # re-apply the reproducer's test-scope dep (e.g. mockito-core) the reset wiped — WITHOUT this a
    # mock-based regression test (the dominant repro style here) fails to COMPILE on /src/new, reads as
    # not-failing, and a GENUINE bug is wrongly rejected. solve() does the same; the flip must mirror it.
    _write_build_edit(root_new, be_path, be_src)
    rc_new, out_new = _sandbox.exec_(cmd, version="new")
    new_fails = _trace_shows_fail({"trace": out_new})
    # materialize the FULL test scaffolding into /src/old (not just the named test) so a multi-file test still
    # compiles there — otherwise it fails on a missing helper stub, not on the bug, and the flip can't fire.
    if _write_scaffold(root_old, scaffold) == 0:
        return (False, new_fails, False)
    _write_build_edit(root_old, be_path, be_src)
    rc_old, out_old = _sandbox.exec_(cmd, version="old")
    old_passes = _trace_shows_pass({"trace": out_old, "rc": rc_old})
    return (True, new_fails, old_passes)


def _validate_test_agent(s, verdict):
    """Critic subagent: does this failing test really demonstrate the suspicion? Fail-OPEN on an LLM error
    (don't lose a real bug to a flaky call — the solver's reward is the backstop)."""
    msg = (f"SUSPICION:\nobservation: {s.observation}\nsuspected_bug: {s.suspected_bug}\nlocation: {s.location}\n\n"
           f"FAILING TEST ({verdict.get('test_path','')}):\n{str(verdict.get('test_src',''))[:4000]}\n\n"
           f"IT FAILED WITH:\n{str(verdict.get('reproduction',''))[:1500]}\n\nDoes it genuinely demonstrate the bug?")
    try:
        ans = (_llm_call(TEST_CRITIC_SYS, msg) or "").strip()
    except Exception:  # noqa: BLE001
        return True, "critic-error (fail-open)"
    if ans.upper().startswith("APPROVE"):
        return True, "critic approved"
    return False, ("critic " + ans[:100])


def _validate_bug(s, verdict):
    """Gate a confirmed verdict before it becomes a Bug. Flip first (executable, ungameable); fall back to the
    critic when the flip can't settle it. Returns (approved, reason)."""
    ran, new_fails, old_passes = _flip_check(verdict)
    if ran and not new_fails:
        return False, "test does not fail on /src/new"        # not actually red -> nothing demonstrated
    if ran and new_fails and old_passes:
        return True, "flip"                                   # red on new, green on old -> real regression
    return _validate_test_agent(s, verdict)                   # no decisive flip -> ask the critic


def _modules_with_files(repo_dir):
    """Group the repo's source files by MODULE (the src/main/java root above them), for the harness's
    repo -> module -> file descent. Returns [(module_rel, [file_rel, ...]), ...] in a stable order."""
    from collections import OrderedDict
    mods = OrderedDict()
    for rel in _source_files(repo_dir):
        norm = rel.replace("\\", "/")
        i = norm.find("/src/main/java/")
        mod = norm[:i] if i >= 0 else "."
        mods.setdefault(mod, []).append(rel)
    return list(mods.items())


def _file_of(location):
    """The bare filename of a suspicion's location — binds a suspicion to the FILE it was raised in."""
    return (location or "").split(":")[0].replace("\\", "/").split("/")[-1]


def _fix_one_file(repo_dir, rel, by_id, conf_floor, max_checks_per_file, log):
    """The fix-java-bugs skill applied to ONE file (the harness's leaf unit): FIND (investigate_file) ->
    PROVE (reproduce, a failing test) -> FIX (solve, the root cause) for each of THIS file's suspicions.
    The portable skills/fix-java-bugs/SKILL.md is the standalone single-agent version of this same procedure.
    Returns the number of reproduce checks it spent."""
    investigate_file(repo_dir, rel)                    # FIND — this file is the entrance point
    _store_to_suspicions(by_id)
    fname = rel.replace("\\", "/").split("/")[-1]
    fchecks = 0
    while fchecks < max_checks_per_file:
        _store_to_suspicions(by_id)                    # pick up anything the reproducer just raised
        pending = [s for s in by_id.values()
                   if s.status == "pending" and s.confidence >= conf_floor and _file_of(s.location) == fname]
        if not pending:
            break
        s = schedule(pending)                          # surest first
        res = reproduce(repo_dir, s)                   # PROVE with a failing test
        fchecks += 1
        verdict = str(res.get("verdict", "inconclusive")).lower()
        if verdict == "confirmed":
            ok, how = _validate_bug(s, res)            # GATE: the test must really demonstrate the bug
            if ok:
                s.status = "proven"
                bug = _add_bug(s, res, validation=how)
                log(f"    [S{s.id}] PROVEN -> Bug[{bug.id}] ({bug.repro_kind}; {how}) — {s.suspected_bug[:60]}")
                if bug.test_src.strip():
                    fx = solve(repo_dir, bug)          # FIX the root cause; test red -> green
                    sol = _add_solution(bug, fx)
                    log(f"      solve Bug[{bug.id}]: {'FIXED' if sol.fixed else 'no fix'} "
                        f"({sol.lines_changed} lines, reward={sol.reward}{', TEST TOUCHED!' if sol.test_changed else ''})")
                else:
                    log(f"      Bug[{bug.id}]: no unit test ({bug.repro_kind}) — left for the author, not guessed")
            else:
                s.status = "inconclusive"
                log(f"    [S{s.id}] REJECTED test ({how}) — not a bug — {s.suspected_bug[:60]}")
        else:
            s.status = verdict
            log(f"    [S{s.id}] {verdict}/{res.get('repro_kind') or '-'} — {s.suspected_bug[:60]}")
    return fchecks


def run_suspicion_review(repo_dir, pr_input, conf_floor=0.4, max_checks_per_file=12, log=print):
    # repo -> module -> file descent — the fix-java-bugs skill applied FILE BY FILE. The harness opens the
    # repo, iterates its modules, and inside each iterates the source FILES; each file is one self-contained
    # find -> prove -> fix unit (_fix_one_file). Coverage is structural (every module, every file addressed);
    # each file proves + fixes its OWN bugs, so there is no global reproduce cap. pr_input is kept only as
    # context for the final synthesize() writeup; it does NOT scope what the harness looks at.
    ctx = pr_input
    _reset_store()
    by_id = {}
    modules = _modules_with_files(repo_dir)
    nfiles = sum(len(fs) for _, fs in modules)
    log(f"repo -> {len(modules)} modules, {nfiles} source files (repo -> module -> file)")
    checks = 0
    for mi, (module_rel, files) in enumerate(modules, 1):
        log(f"module [{mi}/{len(modules)}] {module_rel or '.'} : {len(files)} files")
        for fi, rel in enumerate(files, 1):
            log(f"  file [{fi}/{len(files)}] {rel}")
            checks += _fix_one_file(repo_dir, rel, by_id, conf_floor, max_checks_per_file, log)

    # Stragglers: a reproducer can raise a suspicion in a file already passed (extra_bugs_found). Drain any
    # left pending so a confirmable bug is never silently dropped.
    _store_to_suspicions(by_id)
    for s in sorted([x for x in by_id.values() if x.status == "pending" and x.confidence >= conf_floor],
                    key=lambda x: -x.confidence):
        if checks >= nfiles + 40:                      # bound the straggler drain
            break
        res = reproduce(repo_dir, s); checks += 1
        if str(res.get("verdict", "inconclusive")).lower() == "confirmed":
            ok, how = _validate_bug(s, res)
            if ok:
                s.status = "proven"; bug = _add_bug(s, res, validation=how)
                if bug.test_src.strip():
                    _add_solution(bug, solve(repo_dir, bug))
            else:
                s.status = "inconclusive"
        else:
            s.status = str(res.get("verdict", "inconclusive")).lower()
    _store_to_suspicions(by_id)

    # PHASE 4 — PR: the writer reads the registry (bugs + solutions) and the open suspicions.
    open_suspicions = [s for s in by_id.values() if s.status == "inconclusive"]
    refuted = sum(1 for s in by_id.values() if s.status == "refuted")
    solved = sum(1 for sol in _SOLUTIONS if sol.fixed)
    log(f"=> bugs {len(_BUGS)} ({solved} fixed) | inconclusive {len(open_suspicions)} | "
        f"refuted {refuted} | suspicions {len(by_id)} | checks {checks}")
    review = synthesize(ctx, _BUGS, _SOLUTIONS, open_suspicions)
    return review, {"suspicions": list(by_id.values()), "bugs": list(_BUGS), "solutions": list(_SOLUTIONS)}


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
    # investigate_repo's repo_map + version-aware reads need a live session (the post-PR worktree),
    # so start the per-PR sandbox even for the generator-only probe; reproduce/solve are skipped.
    os.makedirs("results/probes", exist_ok=True)
    open(f"results/probes/{tag}.log", "w").close()
    jdk = _sandbox.detect_jdk(d)
    print(f"=== sandbox JDK for {repo}#{pr}: {jdk} ===", flush=True)
    _sandbox.start(repo, pr, jdk=jdk, log_path=f"results/probes/{tag}.log")
    t0 = _t.time()
    try:
        investigate_repo(d)         # whole-repo is the only investigation mode
    finally:
        _sandbox.stop()
    by_id = {}
    _store_to_suspicions(by_id)
    print(f"\n=== GEN PROBE {repo}#{pr} (whole-repo): {len(by_id)} suspicions in {_t.time()-t0:.0f}s ===")
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
        review, reg = run_suspicion_review(d, pi, conf_floor=conf_floor)
    finally:
        _sandbox.stop()
    os.makedirs("results/susp_runs", exist_ok=True)
    suspicions, bugs, solutions = reg["suspicions"], reg["bugs"], reg["solutions"]
    # The registry, dumped as three linked entry lists: suspicion -> bug (suspicion_id) -> solution (bug_id).
    out = {"repo": repo, "pr": pr, "review": review,
           "n_suspicions": len(suspicions),
           "bugs": len(bugs),
           "solved": sum(1 for sol in solutions if sol.fixed),
           "inconclusive": sum(1 for s in suspicions if s.status == "inconclusive"),
           "refuted": sum(1 for s in suspicions if s.status == "refuted"),
           "registry": {"suspicions": [asdict(s) for s in suspicions],
                        "bugs": [asdict(b) for b in bugs],
                        "solutions": [asdict(sol) for sol in solutions]}}
    json.dump(out, open(f"results/susp_runs/{tag}.json", "w"), indent=1)
    print("\n=== REVIEW ===\n" + review)
    return review, reg


# --- adversarial real-bug judge: the STRICT PR-worthiness filter --------------------------------------
# The head-hunt's critic gate is lenient (precision ~20%): it confirms many test-backed "bugs" that are
# really the code's INTENDED behavior (savepoint dirty-state, URL/enum/equals, CharSequence pedantry). This
# judge is the strict, default-REJECT gate before a candidate becomes a PR — a skeptical maintainer with
# repo-at-HEAD read access arguing AGAINST the bug. Only 'real' verdicts proceed to prepare_pr.
_JUDGMENT = {}


def _reset_judgment():
    _JUDGMENT.clear()


class RecordJudgmentAction(Action):
    verdict: str = Field(description="real | intended | unsure — is the suspected bug a GENUINE defect a "
                         "maintainer would fix, the code's INTENDED/documented behavior, or undecidable? "
                         "Default to intended/unsure unless the code clearly shows a real defect.")
    reason: str = Field(description="one or two sentences citing the evidence (code/Javadoc/tests/contract) "
                        "for why it is real vs intended.")


class RecordJudgmentObservation(Observation):
    pass


_JUDGE_DESC = ("Record your verdict — real | intended | unsure — on whether the suspected bug is a genuine "
               "defect or the code's intended behavior, ONCE, after investigating. Default to intended/unsure "
               "unless the evidence clearly shows a real defect.")


class _RecordJudgmentExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _JUDGMENT["verdict"] = str(action.verdict).lower().strip()
        _JUDGMENT["reason"] = str(action.reason)
        return RecordJudgmentObservation.from_text(text=f"recorded judgment: {_JUDGMENT['verdict']}")


class RecordJudgmentTool(ToolDefinition[RecordJudgmentAction, RecordJudgmentObservation]):
    def declared_resources(self, action):  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state) -> "Sequence[RecordJudgmentTool]":  # noqa: ARG003
        return [cls(description=_JUDGE_DESC, action_type=RecordJudgmentAction,
                    observation_type=RecordJudgmentObservation,
                    annotations=ToolAnnotations(title="record_judgment", readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=False, openWorldHint=False),
                    executor=_RecordJudgmentExecutor())]


JUDGE_SYS = """You are a SKEPTICAL senior maintainer deciding whether a reported bug is real BEFORE it
becomes a pull request. Default to REJECT: most reports are the code's intended or documented behavior, an
edge case the author deliberately chose, or a misreading of the contract. Approve as 'real' ONLY when the
actual code shows a genuine defect a maintainer would fix — a wrong result, a crash on valid input, or a
contract violation the author did not intend.

You have read tools over the repository at its current HEAD. Investigate: read the real method, its callers,
its Javadoc/comments, sibling implementations, and the existing tests. A test that merely asserts a DIFFERENT
design choice is NOT a bug. Ask whether the behavior is deliberate (documented, tested, consistent with
siblings, a sane design) or a true defect. When you cannot tell, say 'unsure' — do not guess 'real'.

Two calibrations: (1) "no internal caller" is NOT a reason to reject — a PUBLIC, non-@Deprecated method that
throws (AIOOBE/NPE/etc.) on input or state reachable through the public API is a REAL bug even if nothing in
this repo currently calls that path; the API surface is the contract. (2) Distinguish a genuine crash on
valid input (real) from strict-but-deliberate rejection of malformed input (often intended) — gauge it
against how the surrounding code treats similar cases. Record once with record_judgment(verdict, reason)."""


def judge_bug(repo_dir, bug):
    """Strict adversarial verdict on one candidate (a bug dict from the registry). Default unsure on failure."""
    _reset_judgment()
    msg = (f"SUSPECTED BUG:\nobservation: {bug.get('observation', '')}\nsuspected_bug: {bug.get('suspected_bug', '')}\n"
           f"location: {bug.get('location', '')}\n\nThe reporter's test (what they claim SHOULD happen):\n"
           f"{str(bug.get('test_src', ''))[:2500]}\n\nInvestigate the real code at HEAD and decide: a genuine "
           "defect, or the code's intended behavior? Reject unless clearly a real defect. Record your verdict.")
    out = _run_agent(JUDGE_SYS, msg, repo_dir, base=("search", "grep", "glob", "file_editor"),
                     extra_tools=["record_judgment"])
    return dict(_JUDGMENT) if _JUDGMENT.get("verdict") else {"verdict": "unsure", "reason": (out or "")[-200:]}


def run_judge(repo):
    """Run the strict judge over every candidate bug in a repo's head registry; write the shortlist."""
    from current_version.repo import ensure_repo_head
    d, _sha = ensure_repo_head(repo)
    if d is None:
        raise RuntimeError(f"could not checkout HEAD for {repo}")
    tag = repo.replace('/', '__') + '__head'
    reg = json.load(open(f"results/susp_runs/{tag}.json"))["registry"]
    os.environ["REASONING_LOG"] = f"results/reasoning/{tag}__judge.log"
    open(os.environ["REASONING_LOG"], "w").close()
    results = []
    for b in reg["bugs"]:
        j = judge_bug(str(d), b)
        results.append({"id": b["id"], "suspected_bug": b["suspected_bug"][:90], "location": b.get("location", ""),
                        "verdict": j["verdict"], "reason": j.get("reason", "")[:200]})
        print(f"  Bug[{b['id']}] {j['verdict'].upper()}: {b['suspected_bug'][:60]}", flush=True)
    os.makedirs("results/judged", exist_ok=True)
    json.dump({"repo": repo, "results": results}, open(f"results/judged/{tag}.json", "w"), indent=1)
    real = [r for r in results if r["verdict"] == "real"]
    print(f"=> {len(real)}/{len(results)} judged REAL for {repo}", flush=True)
    return results


def _setup_head(repo):
    """Whole-repo HEAD review (no PR): checkout the latest default branch, build a minimal context."""
    from current_version.repo import ensure_repo_head
    d, sha = ensure_repo_head(repo)
    if d is None:
        raise RuntimeError(f"could not checkout HEAD for {repo} — clone it first (clone_head)")
    d = str(d)
    pi = (f"Repository: {repo}\nReviewing the LATEST default-branch HEAD ({(sha or '')[:12]}) for real bugs — "
          "whole-repo, no pull request. Find concrete bugs in the current code.")
    tag = repo.replace('/', '__') + '__head'
    os.makedirs("results/reasoning", exist_ok=True)
    os.environ["REASONING_LOG"] = f"results/reasoning/{tag}.log"
    open(os.environ["REASONING_LOG"], "w").close()
    return d, pi, tag, sha


def run_head(repo, conf_floor=0.4):
    """Hunt bugs in a repo's latest HEAD (mode=repo) and write the registry — same gated pipeline, no PR."""
    d, pi, tag, sha = _setup_head(repo)
    os.makedirs("results/probes", exist_ok=True)
    open(f"results/probes/{tag}.log", "w").close()
    jdk = _sandbox.detect_jdk(d)
    print(f"=== HEAD bug-hunt {repo}@{(sha or '')[:12]} | JDK {jdk} ===", flush=True)
    _sandbox.start(repo, "head", jdk=jdk, log_path=f"results/probes/{tag}.log", new_ref="HEAD")
    try:
        review, reg = run_suspicion_review(d, pi, conf_floor=conf_floor)
    finally:
        _sandbox.stop()
    os.makedirs("results/susp_runs", exist_ok=True)
    suspicions, bugs, solutions = reg["suspicions"], reg["bugs"], reg["solutions"]
    out = {"repo": repo, "head_sha": sha, "review": review,
           "n_suspicions": len(suspicions), "bugs": len(bugs),
           "solved": sum(1 for s in solutions if s.fixed),
           "registry": {"suspicions": [asdict(s) for s in suspicions],
                        "bugs": [asdict(b) for b in bugs],
                        "solutions": [asdict(s) for s in solutions]}}
    json.dump(out, open(f"results/susp_runs/{tag}.json", "w"), indent=1)
    print("\n=== REVIEW ===\n" + review)
    return review, reg


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "head":          # suspicion.py <repo> head  -> whole-repo HEAD hunt
        run_head(sys.argv[1])
    elif len(sys.argv) > 2 and sys.argv[2] == "judge":       # suspicion.py <repo> judge -> strict real-bug filter
        run_judge(sys.argv[1])
    elif len(sys.argv) > 3 and sys.argv[3] == "gen":
        gen_probe(sys.argv[1], int(sys.argv[2]))
    else:
        run(sys.argv[1], int(sys.argv[2]))
