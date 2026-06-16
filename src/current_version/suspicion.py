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


def _store_add(claim, location, severity, confidence, expected="", actual=""):
    sid = len(_STORE)
    _STORE.append({"id": sid, "claim": str(claim), "location": str(location),
                   "severity": str(severity).lower(), "confidence": confidence,
                   "expected": str(expected), "actual": str(actual)})
    return sid


_VERDICT = {}   # the fact-checker writes its verdict here via the record_verdict tool (not parsed prose)


def _reset_verdict():
    _VERDICT.clear()


class AddSuspicionAction(Action):
    claim: str = Field(description="The suspected PROBLEM, in one line.")
    location: str = Field(description="File.java:line or area where it is.")
    expected: str = Field(description="What CORRECT behavior would be, and roughly WHERE that is grounded "
                          "(a contract, a sibling/precedent, a test, a convention) — not your taste. A quick "
                          "hypothesis, not a proven claim.")
    actual: str = Field(description="The SPECIFIC differing thing you SUSPECT the code does — a concrete, "
                        "falsifiable guess (a specific wrong value/symbol/case), NOT a vague 'may/might/could'. "
                        "You need NOT have verified it; the prover will. Just name the concrete suspicion.")
    severity: str = Field(description="critical | high | medium | low (impact IF the problem is real).")
    confidence: float = Field(description="0-1, your prior that it is real, before fact-checking.")


class AddSuspicionObservation(Observation):
    pass


_ADD_DESC = ("Record ONE suspicion — a candidate DEFECT to prove later, NOT a confirmed finding. A "
             "suspicion must be a FALSIFIABLE defect: you must state `expected` (correct behavior, "
             "grounded in a contract/sibling/test/spec) and `actual` (the SPECIFIC differing thing the "
             "code does — a concrete value/symbol, not 'may/might'). If you cannot fill expected≠actual "
             "concretely, it is a chore or a speculation — do NOT raise it. Call once per suspicion. "
             "Args: claim, location, expected, actual, severity (critical/high/medium/low), confidence (0-1).")


class _AddSuspicionExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        sid = _store_add(action.claim, action.location, action.severity, action.confidence,
                         action.expected, action.actual)
        return AddSuspicionObservation.from_text(text=f"recorded suspicion #{sid}: {str(action.claim)[:60]}")


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


# --- record_verdict: the fact-checker's decision is CAPTURED BY A TOOL, not parsed from prose ---
# The loop used to regex the final message for {"verdict":...}; when the model wrote its decision in
# prose ("the logger issue — confirmed, uses ReflectiveHierarchyStep.class") the parse failed and the
# verdict SILENTLY defaulted to "partial", losing real confirms (richer post-PR context made the model
# more discursive, exposing this). A tool call is robust to verbosity — same fix add_suspicion already is.
class RecordVerdictAction(Action):
    verdict: str = Field(description="confirmed | refuted. confirmed ONLY if your PROOF shows actual != "
                         "expected (a real defect). If the proof shows they match, or you could not build "
                         "a proof, the verdict is refuted. (partial only for a genuinely-substantive issue "
                         "that no static read AND no runnable test could settle.)")
    proof_kind: str = Field(description="static | dynamic | none. static = a read/grep shows the wrong "
                            "value/symbol literally present (or absent). dynamic = you wrote & RAN a test "
                            "in sandbox_exec and report its result. none = you could not prove it.")
    proof: str = Field(description="The PROOF itself: for static, the file:line + the exact text shown; "
                       "for dynamic, the command you ran and its actual output (pass/fail). This must "
                       "demonstrate actual vs expected, not assert it.")
    evidence: str = Field(description="One-line summary: file:line + the concrete defect (or why refuted).")


class RecordVerdictObservation(Observation):
    pass


_VERDICT_DESC = ("Record your decision on the one suspicion, ONCE, LAST. You are a PROVER, not a judge: "
                 "verdict=confirmed REQUIRES a proof that `actual` != `expected` — either `static` (a "
                 "read/grep showing the wrong value literally present/absent) or `dynamic` (a test you "
                 "wrote and RAN in sandbox_exec, reporting its pass/fail output). If the code matches "
                 "expected, or the concern is speculative/idiomatic/in test-tooling and you cannot build a "
                 "proof, record refuted (proof_kind=none). Do not confirm a plausibility. "
                 "Args: verdict, proof_kind (static/dynamic/none), proof (the actual evidence/test output), evidence.")


class _RecordVerdictExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        _VERDICT["verdict"] = str(action.verdict).lower().strip()
        _VERDICT["proof_kind"] = str(action.proof_kind).lower().strip()
        _VERDICT["proof"] = str(action.proof)
        _VERDICT["evidence"] = str(action.evidence)
        # guard: a 'confirmed' with no proof is exactly the failure mode we are killing — downgrade it.
        if _VERDICT["verdict"] == "confirmed" and _VERDICT["proof_kind"] not in ("static", "dynamic"):
            _VERDICT["verdict"] = "refuted"
            return RecordVerdictObservation.from_text(
                text="confirmed REQUIRES proof_kind=static|dynamic with real proof; none given -> recorded refuted")
        return RecordVerdictObservation.from_text(text=f"recorded verdict: {_VERDICT['verdict']} ({_VERDICT['proof_kind']})")


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

GENERATOR_SYS = """You raise SUSPICIONS about a Java pull request — candidate DEFECTS for a PROVER to
check later, NOT confirmed findings. The PR diff is provided, and your workspace is the POST-PR code;
glance with search/grep/file_editor where a quick look helps. You HYPOTHESIZE; you do NOT prove.

CRITICAL — work FAST and shallow. Do NOT deep-read to verify, do NOT build "static proofs", do NOT
confirm anything — that is the prover's job and doing it here is wasted work. The moment a place looks
off, RECORD it and move on. Breadth and speed matter; a separate prover will refute the wrong ones.

A suspicion must be a FALSIFIABLE DEFECT — you must be able to name, as a quick hypothesis (NOT verified):
- expected = what correct behavior would be, roughly grounded (a contract, a sibling/precedent, a test,
  a convention); and
- actual = the SPECIFIC differing thing you SUSPECT the code does — a concrete guess (a specific wrong
  value/symbol/case), NOT a vague "may/might/could".
If you cannot even name a concrete expected≠actual guess, it is a CHORE ("verify X is handled") or a
SPECULATION ("this might be imprecise") — SKIP it; those are exactly what get falsely confirmed.

Cast a WIDE net over falsifiable candidates — correctness bugs, broken contracts, missing null/error
handling, concurrency hazards, resource leaks, wrong API/overload use, copy-paste slips (a class/
constant/field/logger name carried wrong from a sibling), off-by-one, inverted conditions, etc.

RECORD each by calling `add_suspicion` (claim, location, expected, actual, severity, confidence=0-1 prior
it's real pre-proof) — once per suspicion, the moment you notice it; do not keep them in your head, do not
prove them, do not write a review. When you have swept the diff for falsifiable suspicions, finish."""

SCHEDULER_SYS = """You pick which pending SUSPICION to fact-check next. Choose the one whose
verification is most valuable now — high severity AND genuinely uncertain (a high-impact claim that is
plausible but not yet confirmed). Return ONLY {"id": N} for the chosen suspicion."""

FACT_CHECKER_SYS = """You are a PROVER. You are handed ONE suspicion — a defect HYPOTHESIS with an
`expected` (correct behavior, grounded) and an `actual` (the specific differing thing). Your job is NOT
to reason about whether it's "probably" a bug and opine — it is to PROVE, by reproduction, whether
`actual` really differs from `expected`. The verdict is the OUTCOME of that proof, never your opinion.

Your workspace IS the POST-PR code: `search`/`grep`/`glob`/`file_editor` read the files AS THE PR LEAVES
THEM (added/renamed files ARE on disk). `pr_file_diff` shows the exact change (- = base, + = post-PR).
`sandbox_exec` runs code in a Java sandbox with BOTH trees mounted as normal checkouts (version='new'
post-PR default, 'old' base) — work in /src/new, write a snippet/test, compile, run. Edit/compile freely:
the tree auto-resets to pristine before the next suspicion, and `reset_workspace` resets it on demand.

Build the CHEAPEST sufficient PROOF:
- STATIC proof — when the defect is a literal fact: a read/grep shows the wrong value/symbol literally
  PRESENT (a wrong class/constant/logger name, an off-by-one constant) or a required thing literally
  ABSENT (an unregistered attribute, a missing guard). The reading IS the proof: actual != expected, on
  the page. Use this for mechanical slips — no test needed.
- DYNAMIC proof — when the defect is BEHAVIORAL or NUMERIC (a comparator-contract violation, a precision
  loss, an NPE, a wrong result, a locale surprise): WRITE a tiny test that asserts `expected`, compile and
  RUN it in `sandbox_exec`, and read the result. A FAILING test (actual != expected, shown by the run) =
  confirmed. A PASSING test = refuted. Construct the concrete failing input; if you cannot make a test
  fail, the defect is not real.

Then REFUTE — decisively — whenever you cannot produce such a proof:
- the code matches `expected` (correct / intentional / by-design / guarded) — your own analysis saying
  "this is correct" or "this is intended" IS a refutation, record it as refuted;
- the concern is speculative ("may/might/could") and you cannot build a test that actually fails;
- the claim depends on an EXTERNAL library/service or behavior you cannot read or run;
- the observation is factually true but harmless / idiomatic / in test or build tooling.
An un-disproven worry is NOT a finding. Confirming a plausibility is exactly how false findings survive.

While reading, if you NOTICE a DIFFERENT falsifiable defect (with its own expected≠actual), record it
with `add_suspicion`. For THIS suspicion, RECORD your decision by CALLING `record_verdict` — once, last —
with verdict, proof_kind (static|dynamic|none), proof (the actual file:line text OR the command + its
run output), and a one-line evidence summary. The prose is not read; only the tool call is. confirmed
REQUIRES proof_kind static or dynamic carrying real proof — a confirmed with proof_kind=none is rejected."""

SYNTHESIZER_SYS = """You write the final Java code review from CONFIRMED findings only. Each confirmed
finding becomes a point with its file:line and the evidence. Add NO new claims of your own.

CURATE the OPEN QUESTIONS (partials) hard — do not dump them all. MERGE any that restate the same
underlying concern into ONE question; DROP any that are speculative, already answered by the diff, or
rest on a false premise; keep only the few genuinely-uncertain, substantive ones, clearly hedged and
never as definite claims. A short, sharp review beats a flood of vague questions — a reviewer who asks
ten hedged questions about one concern is noise, and noise costs credibility.

Output SUMMARY: then POINTS:, each point as - [path/File.java:line] <point>."""


SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class Suspicion:
    id: int
    claim: str
    location: str
    severity: str
    confidence: float
    expected: str = ""
    actual: str = ""
    status: str = "pending"           # pending / confirmed / refuted / partial
    evidence: str = ""
    proof_kind: str = ""              # static / dynamic / none — how a confirm was proven
    proof: str = ""                   # the proof itself (file:line text, or command + run output)

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
                       ("record_verdict", RecordVerdictTool), ("reset_workspace", ResetWorkspaceTool)):
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
                by_id[d["id"]] = Suspicion(id=d["id"], claim=d["claim"], location=d["location"],
                                           severity=d["severity"], confidence=float(d["confidence"]),
                                           expected=d.get("expected", ""), actual=d.get("actual", ""))
            except Exception:  # noqa: BLE001
                pass


def generate(repo_dir, ctx):
    _run_agent(GENERATOR_SYS, "PULL REQUEST:\n" + ctx +
               "\n\nRaise the suspicions now — call add_suspicion once for each.",
               repo_dir, extra_tools=[CAPTURE])
    by_id = {}
    _store_to_suspicions(by_id)
    return by_id


def schedule(pending):
    lst = "\n".join(f"[{s.id}] sev={s.severity} conf={s.confidence} :: {s.claim} ({s.location})"
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


def fact_check(repo_dir, s):
    # LEAN context (root-cause fix for the 400 that crashed 6222): a fact-check verifies ONE
    # suspicion, so it gets the suspicion and reads the actual code ON DEMAND via the tools (the
    # sandbox sees the real repo). Passing the whole ~150k-char PR context here overflowed
    # max-model-len across the multi-turn agent — and was lost-in-the-middle and costly anyway.
    _reset_verdict()
    _sandbox.reset_clean()   # pristine source for THIS check — wipe what the previous prover wrote/built
    msg = (f"SUSPICION TO PROVE:\nclaim: {s.claim}\nlocation: {s.location}\n"
           f"expected: {s.expected or '(not stated — derive it, grounded)'}\n"
           f"actual:   {s.actual or '(not stated — pin the concrete differing thing)'}\n\n"
           "PROVE whether actual != expected. Build the cheapest sufficient proof: STATIC (read/grep shows "
           "the wrong value/symbol literally present or absent) for a mechanical slip; DYNAMIC (write a test "
           "asserting `expected`, compile and RUN it via `sandbox_exec` — a FAILING run = confirmed, a PASSING "
           "run = refuted) for a behavioral/numeric claim. If the code matches expected, or the worry is "
           "speculative/external/idiomatic and you cannot build a failing proof — REFUTE. Record any NEW "
           "falsifiable defect with add_suspicion. When proven, call `record_verdict` (verdict, proof_kind "
           "static|dynamic|none, proof = the file:line text or command+output, evidence) — once, last.")
    out = _run_agent(FACT_CHECKER_SYS, msg, repo_dir,
                     extra_tools=[CAPTURE, "sandbox_exec", "record_verdict", "reset_workspace"])
    if _VERDICT.get("verdict") in ("confirmed", "refuted", "partial"):   # tool-captured: robust
        return dict(_VERDICT)
    j = _extract_json(out, "{")                                          # fallback: a JSON blob in text
    if isinstance(j, dict) and str(j.get("verdict", "")).lower() in ("confirmed", "refuted", "partial"):
        return {"verdict": str(j["verdict"]).lower(), "evidence": str(j.get("evidence", ""))}
    print(f"  [verdict] no record_verdict + no JSON for S[{s.id}] — defaulting refuted (no proof)", flush=True)
    return {"verdict": "refuted", "evidence": (out or "")[-300:], "proof_kind": "none"}


def synthesize(ctx, confirmed, partials):
    body = "CONFIRMED FINDINGS (each PROVEN: expected != actual):\n" + ("\n".join(
        f"- [{s.location}] {s.claim}\n    expected: {s.expected}\n    actual: {s.actual}\n"
        f"    proof ({s.proof_kind}): {s.evidence}" for s in confirmed) or "(none)")
    if partials:
        body += "\n\nOPEN QUESTIONS (partial — include as hedged questions):\n" + "\n".join(
            f"- {s.claim} [{s.location}]" for s in partials)
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
        log(f"   S[{s.id}] v={s.value():.1f} sev={s.severity} conf={s.confidence} :: {s.claim[:72]}{mark}")
    checks = 0
    while checks < max_checks:
        _store_to_suspicions(by_id)            # pick up any new suspicions recorded by fact-checks
        # gate on CONFIDENCE (is it worth verifying), not severity — a certain low-impact bug is
        # still a finding. Severity only sets the order (schedule()). The fact-check is the filter.
        pending = [s for s in by_id.values() if s.status == "pending" and s.confidence >= conf_floor]
        if not pending:
            break
        s = schedule(pending)
        before = len(_STORE)
        res = fact_check(repo_dir, s)
        s.status = str(res.get("verdict", "refuted")).lower()
        s.evidence = str(res.get("evidence", ""))[:600]
        s.proof_kind = str(res.get("proof_kind", ""))
        s.proof = str(res.get("proof", ""))[:600]
        checks += 1
        log(f"  check {checks}: [{s.id}] {s.status}/{s.proof_kind or '-'} (+{len(_STORE) - before} new) — {s.claim[:62]}")
    confirmed = [s for s in by_id.values() if s.status == "confirmed"]
    partials = [s for s in by_id.values() if s.status == "partial"]
    refuted = sum(1 for s in by_id.values() if s.status == "refuted")
    log(f"=> confirmed {len(confirmed)} | partial {len(partials)} | refuted {refuted} | "
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
        print(f"  S[{s.id}] sev={s.severity} conf={s.confidence} :: {s.claim[:80]}")
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
