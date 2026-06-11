# Mental model: how the orchestrator + subagents actually work (from 37-PR v2 dialogs)

## The mechanism
1. **Orchestrator** (no file tools) gets the PR diff + the FULL changed files. It reasons,
   then **delegates investigation tasks** to read-only subagents (3 at a time is typical).
2. Each **subagent** starts fresh: `[system prompt + a full copy of the changed-files
   injection + ONE task prompt]` (nmsgs=2). It uses `search`/grep/glob/file_editor to
   explore SURROUNDING base code, then returns a concise grounded finding.
3. Orchestrator appends each finding to its (growing) context, may delegate MORE rounds,
   then synthesizes the final review.

Isolation works (orchestrator stays lean; subagents don't see each other). The problems
are **calibration** (when to stop) and **scope** (what to investigate) — not the architecture.

## Weaknesses (quantified across 37 PRs)

### W1 — Orchestrator delegates in WAVES with no upfront plan  (16/37 PRs multi-wave)
It does "delegate 3 → read findings → think of more → delegate 3 more," repeatedly. On
netty#14487: 6 rounds, 10 tasks; each round it says *"now I have a good picture"* then
delegates again (*"let me check one more thing"*). No investigation plan, no convergence
criterion. Cost compounds: every new wave re-sends the whole growing findings context AND
spawns fresh subagents (each paying the injection tax, W4).

### W2 — Orchestrator delegates DOOMED tasks for PR-added files
netty round 1 delegated "find the full content of IoUringFileRegion.java" — a file ADDED
by the PR, not on disk at base. Round 2's thought: *"they don't exist in the base commit,
so I can't investigate them."* A whole wave wasted; the orchestrator knows the base-commit
rule but doesn't apply it when planning.

### W3 — Subagent has no stop discipline; over-explores tangential code
Subagent turns/session: median 8, **max 25, 18/113 sessions >12 turns**. flink#28256: a
subagent asked about `predicateConstants` followed the call graph into Calcite internals
and *multiple unrelated rules* — *"let me look at AggregateReduceGroupingRule… this rule
doesn't use it. Let me look at Calcite's…"* — 17 turns, context 69k→107k. It answers the
question early but keeps wandering. No "you have enough — report now."

### W4 — Misdirected depth (the −0.6 net cause, refined)
The exploration is BREADTH (call-graph wandering) where it should be DEPTH (verify the
specific impact: who calls/imports the CHANGED symbol). So it both over-explores tangential
code AND under-verifies the thing that scores points → the hedged *trivial* findings from
`v2_intent_analysis.md`. The agent is **uncalibrated**, not uniformly shallow: it stops too
early on simple PRs (accumulo/quarkus/tycho −4) and wanders too far on complex ones (flink).

### W5 — Redundant changed-files injection tax per subagent
Every subagent carries a FULL copy of the changed files: first-message prompt tokens
**median 23.7k, max 69k** — re-sent every turn (median +7.7k growth, max +37.6k). Three
subagents × ~24k base = the bulk of the per-PR prefill, yet their job is SURROUNDING code,
not the changed files (the orchestrator already holds those).

## Fixes, ranked by leverage
1. **Subagent stop-discipline + the `usages` tool** (fixes W3+W4 — the calibration core).
   Prompt: "Answer the SPECIFIC question; verify the changed symbol's callers/impact with
   `usages`; then STOP — do not explore unrelated call-graph code." Recovers depth (net)
   AND cuts over-exploration (tokens) at once. **Top priority.**
2. **Orchestrator: plan-then-batch** (fixes W1). Produce the complete investigation
   question-list up front, delegate in ONE batch, then synthesize. Add a soft budget /
   "you have enough — write the review" convergence nudge. Kills the 16/37 multi-wave
   re-delegation and the compounding orchestrator-context prefill.
3. **Trim the subagent injection to DIFF HUNKS** (fixes W5). Give subagents the diff +
   pointers, not the full changed files (the orchestrator keeps the full copy). Cuts ~24k
   median base prefill × every subagent × every turn.
4. **PR-added-file awareness at the orchestrator** (fixes W2). "Added/renamed files are in
   the diff, not on disk — read them from the diff; never delegate to find them."

## Note
Search adoption is healthy (subagents use it as the primary read tool), and delegation
isolation keeps the orchestrator lean. The wins are in CALIBRATION and SCOPE, which are
prompt/tool fixes, not architectural ones.
