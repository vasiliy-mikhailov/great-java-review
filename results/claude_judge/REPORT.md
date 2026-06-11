# Claude as judge: real numbers for v1–v4 (14 PRs, independent blind review first)

Method: for each PR a Claude grader first wrote its OWN review (diff + repo at base,
candidates unseen), then graded every v1–v4 point against the code (verify before
declaring wrong), counted misses against human ∪ Claude findings, and flagged
"exceeds" — verified findings better than both references.

## Numbers (Claude vs the old Qwen self-judging)
| | v1 grep | v2 search | v3 +focus | v4 +pathnorm |
|---|---|---|---|---|
| Claude net avg | **−2.4** | −2.6 | −2.9 | −3.1 |
| (Qwen self-judge said) | 3.6 | 3.0 | 3.4 | 3.4 |

Buckets (totals over 14 PRs): every version ≈ 30 goods, ~2 criticals, **~24 fabrications,
~50 misses**, and a handful of genuine "exceeds" (v1: 7, v4: 5, v3: 3, v2: 2).

## What this means
1. **The Qwen self-judge was certifying fabrications.** Flagship examples: quarkus#28314 —
   the "removed isClassPresent breaks TracerProcessor" line that Qwen scored as a critical
   find is FALSE (the PR moves all classes and updates TracerProcessor); sevntu#645 — Qwen
   gave v2 +9 for a review Claude scored −13 (phantom APIs, falsely "unused" imports
   against a clean PR). Self-judging shared the reviewer's blind spots exactly as feared.
2. **v1–v4 are statistically indistinguishable on quality** (spread 0.7 vs per-PR swings of
   ±10). The tool iterations moved COST massively and reliably (v1 1.9M → v4 ~1.0M sent
   tokens; path-flail 62%→21%; those are measured, not judged) — but the quality ladder
   the Qwen judge showed was mostly noise.
3. **The dominant defect is upstream of the tools: the truncated diff.** Graders traced the
   fabrications on tycho#1264, Drifty#801, trino#29144, wildfly#6015, quarkus#28314 to the
   same cause — `pr_input` caps the diff (≈7k chars) and the reviewer then asserts "X was
   not updated" about hunks beyond the cut, when the real PR contains them. The repo can't
   refute these (it's at base), so confident false "missing migration" claims survive.
   Fixing input truncation (full diff, or explicit "diff truncated — do not claim
   something is missing beyond this point") attacks ~the largest fabrication class for
   every version at once.
4. **What's good:** all versions reliably catch surface-level realities (typos that shipped,
   action-version inconsistencies, unused imports, NPE paths) and occasionally land gems —
   the "exceeds" list includes v4's CommandUtil-stdout bug and dead-throw-branch insight,
   v1's PathAddress.toString()-as-hostname latent bug.
5. **What's missed (the ~3.6 misses/PR):** deep semantic defects — int truncation breaking
   >2GB FileRegions, ECANCELED regression, lambda-vs-ELIST AST undercounting, gating-all-CI
   design issues. These need the deeper, verified exploration the tools were meant to buy.

## Recommendation
- Treat all prior Qwen-judged conclusions as cost-only; quality conclusions come from
  Claude judging (this report).
- Next highest-leverage fix is not a tool: **stop truncating pr_input** (or teach the
  reviewer the truncation boundary). Then re-run one variant and Claude-judge it.
- Keep v4's toolset for cost (cheapest at equal quality); the focus-language differences
  (v2 vs v3 vs v4) did not survive a trustworthy judge.


---

# FINAL (all 35 judgeable PRs; wildfly#6304 excluded — v2 generation failure)

| | v1 (n=14) | v2 (n=35) | v3 (n=35) | v4 (n=35) |
|---|---|---|---|---|
| Claude net avg | -2.43 | -2.63 | -2.63 | **-2.17** |
| fabrications (wrong) | 23 | 57 | 53 | **47** |
| misses | 50 | 123 | 121 | **118** |
| goods+crits | 36 | 82 | 76 | **83** |
| exceeds | 7 | 7 | **12** | 8 |

Pairwise (paired, n=35): v2-v3 +0.00 ± 0.53; v4 ahead of both v2 and v3 by +0.46
(SE 0.42-0.50, w/t/l 15/7/13 and 15/8/12) — directionally consistent but ~1 SE.

## Final conclusions
1. v4 (search + calm focus + path normalization) is the best configuration: highest
   Claude net, fewest fabrications and misses, most goods, AND the cheapest (~1.0M sent
   tokens vs v1's 1.9M). The quality edge is ~1 SE — modest — but every axis points the
   same way, and the cost edge is unambiguous.
2. All versions remain net-negative under a strict independent judge: the reviewer's
   fabrication rate (~1.5/PR) and miss rate (~3.4/PR) outweigh its real findings. The
   single dominant fabrication driver, confirmed across ~10 PRs by independent graders,
   is the TRUNCATED pr_input: the reviewer asserts "X was not updated" about hunks beyond
   the cut that the real commit contains. Graders that recovered the full commit from
   local git history refuted these claims wholesale.
3. The Qwen self-judge systematically certified these fabrications (e.g. sevntu#645:
   Qwen +9 vs Claude -13). Self-judging is structurally blind to them.
4. Genuine capability exists: 34 'exceeds' findings across versions — verified real bugs
   that neither the human reviewer nor the independent Claude reviewer caught (plaintext
   passwords to Zookeeper would have been adjacent, NaN->1 estimate bug, CommandUtil
   stdout, JavaPoet dead branch). The machinery can find gold; it drowns it in
   truncation-driven noise.

## Next step (highest leverage, in order)
1. Fix pr_input truncation: include the full diff, or annotate the cut and forbid
   absence-claims beyond it (prompt + maybe a `pr_full_diff` tool reading git history,
   which graders proved works).
2. Re-run ONE configuration (v4) with the truncation fix and Claude-judge it: the
   hypothesis is that removing ~1 fabrication/PR and the false-absence class flips the
   net positive.
3. Keep Claude as the only judge; Qwen-judged numbers are cost-telemetry only.

---

# v5 FINAL (all 37 PRs, Claude-judged, paired v5 vs v4)

v5 = v4 (search + calm focus + path normalization) + four fixes derived from tracing v4's
fabrications and misses: (1) full PR diff in pr_input (git fetch pull/N/head; explicit
truncation marker if >150k chars), (2) asymmetric-verification guidance — the repo is at
BASE, so absence in the repo can never prove the PR lacks something, (3) hedge
preservation — the orchestrator must not promote "probably/must be adding" into definite
"missing/broken" claims, (4) findings ledger — investigators report every candidate
issue they notice instead of silently dropping touched leads.

## Numbers (n=37, every PR judged by an independent Claude grader, blind own review first)

| | v4 | v5 |
|---|---|---|
| Claude net avg | −2.32 | **+0.43** |
| paired v5−v4 | — | **+2.76 ± 0.59 SE** (w/t/l 24/5/8) |
| absence-fabrications | 54 | **12** |
| wrong (all fabrication types) | 48 | **16** |
| goods + criticals | 57 | **81** |
| missed | 97 | **84** |
| exceeds | 30 | **46** |
| cost (sent tok/PR, sec/PR) | 1.04M, 399s | 1.23M, 423s |

## Conclusions
1. **v5 is the first net-positive configuration** under a strict independent judge, and
   the margin over v4 is ~4.7 SE — the first quality difference in this project that
   clears statistical noise (v1→v4 spreads were ~1 SE).
2. **The mechanism is exactly the one the trace analysis predicted.** Absence-fabrications
   fell 54→12 (−78%) and total wrong points 48→16. The biggest per-PR swings (+10, +10,
   +9, +8, +8) are precisely the PRs where v4 reviewed its own truncated input — fluo#883,
   trino#5478, Drifty#801, tycho#1264, wildfly#6015. On quarkus#34681, whose diff exceeds
   even the 150k budget, the explicit truncation marker alone kept v5 at zero
   absence-fabrications while v4 produced three.
3. **The full diff did more than remove noise — it added substance.** Goods+criticals rose
   57→81 and "exceeds" findings (verified bugs neither the human nor the independent
   Claude reviewer caught) rose 30→46, including netty#15399's MpscIntQueue
   phantom-slot corruption and the 16-magazine finalize leak.
4. **Cost of the fix is small:** +18% sent tokens, +6% wall time, fewer calls. The diff
   pays for itself by ending the "verify absence against base" wild-goose chases.
5. **What v5 still gets wrong (residual 16 wrongs / 12 absence-fabs):** misreads of
   visible content, dependency/ecosystem claims (stale Node-LTS, Moshi versions),
   build-semantics reasoning, and echoing stale PR descriptions. These are reviewer-model
   reasoning errors, not pipeline artifacts — the natural target for GEPA prompt tuning,
   not more tools.
6. **Where v5 still loses to v4 (8 PRs):** mostly small-diff PRs where v4's truncated
   view was already complete, so v5's extra context only added hedge-padding; the losses
   are −1/−2 sized, while the wins reach +10.

## Project-level answer
The project asked whether repo access makes Qwen's PR reviews better. The honest answer
after Claude-judging every configuration: repo access alone (v1–v4) moved cost, not
quality — every config sat at −2 to −3 net because the reviewer fabricated absences from
a truncated diff faster than tools could add insight. Fixing the input (full diff) plus
teaching the agent what its evidence can and cannot prove (asymmetric verification, hedge
preservation, ledger) flipped the system to net-positive at +0.43 — modest, but real,
paired, and significant. The remaining gap to a good human reviewer is concentrated in
84 misses (deep semantic defects) and 16 reasoning errors — both prompt-genome territory.
