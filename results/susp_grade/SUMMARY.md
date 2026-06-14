# Suspicion vs v8 — graded head-to-head (4 of 8 finished PRs)
Same Claude grader, same rubric, both reviews per PR. Reward conventions:
- search_net (this loop, precision-first) = (#crit+#good) − (#wrong+#fab); NO missed term.
  open-question scoring: real_issue=+1 (good), false_premise=−1 (wrong), speculative=0; duplicates deduped.
- full_net (historical v8 rubric) = 2*crit + good − wrong − fab − missed.

| PR (kind)            | v8 search | susp search | v8 full | susp full | notes |
|----------------------|-----------|-------------|---------|-----------|-------|
| quarkus 6913 (gen)   | +2 | +2 | -1 | 0  | susp CONFIRMED comparator+deadcode (v8 missed both); 1 false-premise Q |
| spring-boot 30358    | +2 | +2 |  0 | 0  | v8 made a WRONG "always-null" critical; susp scoped it correctly as good |
| vert.x 4809 (test)   | +4 | +4 | +1 | 0  | susp caught critical NPE (as a Q) v8 missed; but missed v8's writeWindow point; over-hedged (only 1 confirmed) |
| tycho 5627 (test)    | +3 | +4 |  0 | +2 | susp CONFIRMED doCopyResources+precedence (v8 missed); v8 caught test+release edge susp missed |
| **SUM (4)**          | **+11** | **+12** | **0** | **+2** | |

Fabrication profile: suspicion = 0 asserted-wrong critical claims across all 4; its only errors are hedged false-premise OPEN QUESTIONS. v8 asserted 1 flat-wrong critical (30358). => the fact-check kills fabrications by construction, as designed.
Weakness exposed: suspicion OVER-HEDGES — files real findings as open questions instead of confirming (4809: 1 confirmed / 6 questions), and still misses some real points (writeWindow). Next lever = make the fact-checker/synthesizer confirm more decisively.
