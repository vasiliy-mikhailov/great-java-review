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
from dataclasses import dataclass

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


def _store_add(claim, location, severity, confidence):
    sid = len(_STORE)
    _STORE.append({"id": sid, "claim": str(claim), "location": str(location),
                   "severity": str(severity).lower(), "confidence": confidence})
    return sid


class AddSuspicionAction(Action):
    claim: str = Field(description="The suspected PROBLEM, phrased as something to verify.")
    location: str = Field(description="File.java:line or area where it is.")
    severity: str = Field(description="critical | high | medium | low (impact IF the problem is real).")
    confidence: float = Field(description="0-1, your prior that it is real, before fact-checking.")


class AddSuspicionObservation(Observation):
    pass


_ADD_DESC = ("Record ONE suspicion — a candidate issue to fact-check later, NOT a confirmed "
             "finding. Call this the moment you notice something worth verifying; call it once "
             "per suspicion. Args: claim, location, severity (critical/high/medium/low), confidence (0-1).")


class _AddSuspicionExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        sid = _store_add(action.claim, action.location, action.severity, action.confidence)
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


class SandboxExecObservation(Observation):
    pass


_SBX_DESC = ("Run bash in a Java sandbox container to VERIFY a claim by EXECUTION: write a "
             "tiny program/test reproducing the suspected behavior, `javac` it, `java` it, "
             "and read the result — the compiler resolves overloads/signatures/types exactly "
             "and the runtime shows whether it actually throws/misbehaves. Use it whenever a "
             "claim is checkable by running code rather than only reading it.")


class _SandboxExecExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):  # noqa: ARG002
        rc, out = _sandbox.exec_(action.command)
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


# --- prompts (the genome for this architecture) -----------------------------------------

GENERATOR_SYS = """You raise SUSPICIONS about a Java pull request — candidate issues to fact-check
later, NOT confirmed findings. The PR diff and the base content of the changed files are provided;
use search/grep/file_editor to look closer wherever it helps. For every place a strong reviewer
would pause — a possible correctness bug, broken contract, missing null/error handling, concurrency
hazard, resource leak, wrong API/overload use, untested path, security/escaping gap, behavior change,
copy-paste slip (a class/constant/field/logger name carried over wrong from a sibling), off-by-one,
inverted or incorrect condition, etc. — emit a suspicion. Cast a WIDE net: over-suspect, because a later fact-checker refutes the wrong
ones; a suspicion costs nothing, a missed issue is gone. Each suspicion is a HYPOTHESIS to verify, not
an assertion. RECORD each suspicion by calling the `add_suspicion` tool — once per suspicion, the
moment you notice it (claim = what might be wrong phrased as something to verify; location = File.java:line
or area; severity = critical/high/medium/low impact IF true; confidence = 0-1 prior it's real, pre-check).
Do not emit a JSON list and do not keep them in your head — call the tool for each, so none is lost. Do
not verify here, do not write a review. When you have recorded every suspicion you can find, finish."""

SCHEDULER_SYS = """You pick which pending SUSPICION to fact-check next. Choose the one whose
verification is most valuable now — high severity AND genuinely uncertain (a high-impact claim that is
plausible but not yet confirmed). Return ONLY {"id": N} for the chosen suspicion."""

FACT_CHECKER_SYS = """You FACT-CHECK one suspicion about a Java pull request against the ACTUAL code.
The suspicion is a hypothesis — confirm or refute it by reading the real thing with the tools:
`pr_file_diff` for the exact change to a file (past any truncation), `file_editor`/`search`/`grep` for
base/surrounding code. The repo is at the BASE commit, so added code lives only in the diff.

Be rigorous and skeptical — default to REFUTED unless the code positively proves the claim. Resolve the
real binding before judging:
- a 'removed/deleted' claim: find the actual `-` line in the diff. The line still being in the base file
  on disk does NOT settle it — the diff is the source of truth for what the PR removes.
- a wrong-overload / signature-mismatch claim: find EVERY candidate overload with its exact parameters,
  then match the call by number AND types of arguments (follow the inheritance chain). An apparent
  mismatch is usually you reading the wrong overload.
- a 'missing/conflict/untested' claim: verify against the actual code and the project's conventions.

PROVE it by EXECUTION when you can: you have `sandbox_exec`, a Java sandbox where you write a
tiny program/test reproducing the suspected behavior, compile it (`javac`), and run it. The
compiler resolves overloads/signatures/types EXACTLY (settling any wrong-overload or
"won't compile" claim) and the runtime shows whether the code actually throws or misbehaves
(a comparator-contract violation, an NPE, an off-by-one, a locale surprise). Prefer a run to
an argument. If a claim depends on an EXTERNAL library/service or a behavior you cannot
reproduce or read in the code, you cannot confirm it — REFUTE it (an unverifiable claim is
not a finding; confirming one is how fabrications survive).

While reading, if you NOTICE a DIFFERENT candidate issue, record it with the `add_suspicion` tool
(do not put it in your output). For THIS suspicion, output ONLY JSON:
{"verdict": "confirmed|refuted|partial", "evidence": "<file:line + exactly what the code shows>"}.
A suspicion is a hypothesis of a PROBLEM. Judge the PROBLEM, not the description:
- CONFIRM only when the suspected problem is REAL — the code is actually wrong, unsafe, or will
  misbehave, and the author should act (e.g. a wrong class/constant/logger name literally present, a
  value dereferenced without a guard, an off-by-one, a public-API break). A visible mechanical slip
  counts — you need not prove intent.
- REFUTE when there is NO actual problem — either the code does not do what the suspicion says, OR it
  does but the behavior is correct / intended / harmless. Confirming that the code merely MATCHES a
  neutral description ("X is added at index 4", "the flag is set to false") is NOT a finding — if
  nothing is wrong, REFUTE.
- 'partial' ONLY when you genuinely cannot tell from the visible code; it should be rare.
Bias toward a decisive confirmed/refuted."""

SYNTHESIZER_SYS = """You write the final Java code review from CONFIRMED findings only. Each confirmed
finding becomes a point with its file:line and the evidence. Include the OPEN QUESTIONS (partials) as
questions to the author, clearly hedged — never as definite claims. Add NO new claims of your own.
Output SUMMARY: then POINTS:, each point as - [path/File.java:line] <point>."""


SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class Suspicion:
    id: int
    claim: str
    location: str
    severity: str
    confidence: float
    status: str = "pending"           # pending / confirmed / refuted / partial
    evidence: str = ""

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
        for _n, _t in (("add_suspicion", AddSuspicionTool), ("sandbox_exec", SandboxExecTool)):
            try:
                _register_tool(_n, _t)
            except Exception:  # noqa: BLE001  (already registered)
                pass
        _TOOLS_READY = True
    return [Tool(name=n) for n in ("search", "grep", "glob", "file_editor", "pr_files", "pr_file_diff")]


CAPTURE = "add_suspicion"


def _run_agent(system_prompt, user_msg, repo_dir, extra_tools=()):
    """Run a tool-using agent to completion; return its final (post-think) text."""
    tools = _read_tools() + [Tool(name=n) for n in extra_tools]
    llm = harness._llm("qwen").model_copy(update={"usage_id": "oh_suspicion", "max_output_tokens": 32768})
    agent = Agent(llm=llm, tools=tools, system_prompt=system_prompt, condenser=harness._condenser(llm))
    conv = Conversation(agent=agent, workspace=str(repo_dir), visualizer=harness._NoViz, persistence_dir=None)
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
                                           severity=d["severity"], confidence=float(d["confidence"]))
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


def fact_check(repo_dir, ctx, s):
    msg = ("PULL REQUEST:\n" + ctx + "\n\nSUSPICION TO FACT-CHECK:\n"
           f"claim: {s.claim}\nlocation: {s.location}\n"
           "Verify it against the ACTUAL code. Record any NEW issue you notice with add_suspicion, "
           "then output the JSON {verdict, evidence} for THIS suspicion.")
    return _extract_json(_run_agent(FACT_CHECKER_SYS, msg, repo_dir,
                                    extra_tools=[CAPTURE, "sandbox_exec"]), "{") \
        or {"verdict": "partial"}


def synthesize(ctx, confirmed, partials):
    body = "CONFIRMED FINDINGS:\n" + ("\n".join(
        f"- {s.claim} [{s.location}] :: {s.evidence}" for s in confirmed) or "(none)")
    if partials:
        body += "\n\nOPEN QUESTIONS (partial — include as hedged questions):\n" + "\n".join(
            f"- {s.claim} [{s.location}]" for s in partials)
    txt = _llm_call(SYNTHESIZER_SYS, "PULL REQUEST (context):\n" + ctx[:8000] + "\n\n" + body +
                    "\n\nWrite the review.")
    return final_review(_post_think(txt))


def run_suspicion_review(repo_dir, pr_input, conf_floor=0.4, max_checks=16, log=print):
    files = harness._changed_files_content(repo_dir, pr_input)
    ctx = pr_input + (("\n\n=== FULL CONTENT OF THE CHANGED FILES (base commit) ===\n" + files)
                      if files else "")
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
        res = fact_check(repo_dir, ctx, s)
        s.status = str(res.get("verdict", "partial")).lower()
        s.evidence = str(res.get("evidence", ""))[:600]
        checks += 1
        log(f"  check {checks}: [{s.id}] {s.status} (+{len(_STORE) - before} new) — {s.claim[:70]}")
    confirmed = [s for s in by_id.values() if s.status == "confirmed"]
    partials = [s for s in by_id.values() if s.status == "partial"]
    refuted = sum(1 for s in by_id.values() if s.status == "refuted")
    log(f"=> confirmed {len(confirmed)} | partial {len(partials)} | refuted {refuted} | "
        f"total suspicions {len(by_id)} | checks {checks}")
    review = synthesize(ctx, confirmed, partials)
    return review, list(by_id.values())


def run(repo, pr, conf_floor=0.4):
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
           "n_suspicions": len(sus)}
    json.dump(out, open(f"results/susp_runs/{repo.replace('/', '__')}__{pr}.json", "w"), indent=1)
    print("\n=== REVIEW ===\n" + review)
    return review, sus


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]))
