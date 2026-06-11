# v2 (`search` tool) intent analysis @ n=12 — and the next tool

## Headline
The `search` tool **works as designed on cost** (2.2× fewer sent tokens, ~half the
delegation calls, search-dominated) but introduced a **substance regression** averaging
**net −0.8** vs baseline. The cause is NOT fabrication (judge `wrong=0` on both) — it's
**depth**: search makes exploration so cheap that subagents stop after finding a snippet
and skip the verification that turns an observation into a confirmed finding.

## Evidence
- **Search adoption is partial: 55%** of subagent read-tool calls (274 search vs 222
  grep+file_editor+glob). `file_editor` whole-file views persist (98 calls) — the old habit
  isn't gone.
- **v2 subagents do 8.0 turns/subagent** vs baseline's ~15–24 (attempt_2 probes). Half the
  turns = half the exploration.
- **Only 14%** of subagent turns mention checking callers/usages/impact.
- **Per-PR:** 6 regressions (accumulo#982 −4, quarkus#28314 −4, tycho#1264 −4, dubbo −3,
  netty −3, Drifty −2), offset by a +7 win on sevntu#645 and four +1s.

## Mechanism (from the review diffs)
Same surface observations, scored differently because v2 didn't CONFIRM impact:
- **accumulo#982** (v2 0 / base 4): v2 had good 1 / **trivial 4**; baseline good 5 /
  trivial 1. v2 logged "Good: error handling aligns with convention" as *praise* (trivial);
  baseline framed the SAME facts as actionable findings AND found 4 more, because it read
  the callers (FluoScan.main, etc.) to confirm `System.exit(-1)` is safe.
- **quarkus#28314** (v2 1 / base 5): v2 noted "Truncated diff — *potential* compilation
  break from removed `isClassPresent`" → scored **trivial** (hedged). Baseline **confirmed**
  it: "Removing `isClassPresent()` breaks `TracerProcessor` which static-imports and calls
  it" → good. Baseline also confirmed "OpenTelemetryConfig migration incomplete — 8 runtime
  files still import the old path" by searching all importers. v2 stopped at the snippet.

So the baseline's wasteful grep→view-whole-file loop *incidentally* read surrounding
callers/importers, which let it CONFIRM downstream impact. v2's targeted search returns the
snippet and the agent concludes — under-verifying.

## Re-derived intent → perfect-tool
The dominant REMAINING intent now that "read the code" is solved is:

> **"Confirm the downstream impact of a changed/removed symbol — who calls it, who imports
> it, is the migration complete across all files?"**

`search` *can* do this (grep the symbol repo-wide), but the agent rarely does (14%) because
the follow-up isn't cheap/obvious and nothing prompts it.

**NEXT TOOL: `usages(symbol)`** — a find-references tool returning every call site / import /
reference of a symbol (with file:line + context), optionally filtered to `callers` vs
`imports`. One cheap call answers "what breaks if this changes," converting v2's hedged
*trivial* observations into *confirmed* good findings — recovering substance while keeping
the token savings (one call, not a 15-turn whole-file loop).

Pair it with a **prompt nudge**: "before concluding a changed/removed symbol is safe or
risky, call `usages` to confirm who depends on it." This also addresses the only behavioral
gap (subagents stop early).

## Secondary levers
- Push search adoption past 55% (deprioritize/limit `file_editor` whole-file views).
- Orchestrator over-delegation persists on complex PRs (netty 6 rounds/88 calls, sevntu,
  trino) — an orchestrator-level budget/stop tool is a later candidate, not the next one.

## Verdict
Keep `search` (real cost win). Add **`usages`** + the verify-impact nudge as the next tool;
re-run the A/B and check whether net delta closes to ≥0 at 2× lower cost.
