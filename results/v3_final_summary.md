# v3 (search + focus) — FINAL results @ 37/37

## (1) Three-version paired comparison (n=14, same PRs, same judge)
| version | net | sec | sent tokens |
|---|---|---|---|
| v1 baseline (grep/view) | 3.6 | 627 | 1,923k |
| v2 search | 3.0 | 475 | 1,124k |
| v3 search+focus | 3.4 | 416 | 1,250k |

v3 ≈ v1 quality at **1.5× fewer tokens, 1.5× less time**; v3 > v2 on this set.

## (2) v3 vs v2 on the full mix (n=34 both-judged; 3 generation-failure holes excluded)
- net: **v2 3.7 vs v3 2.4** (v2 +1.3) | sec ~equal | sent ~equal
- v3 w/t/l: 11/4/19
- buckets/PR: v2 crit 0.41 good **3.82** triv 1.71 wrong 0.32 miss 0.59
              v3 crit 0.29 good **3.06** triv 2.35 wrong **0.29** miss 0.94

## (3) Ladder (n=15): does repo exploration pay?
mr 1.5 (1.5k tok) → mr_code 1.7 (20k) → **v3 tools 2.9 (1,186k)** — tools +1.2 over files-only.

## Conclusion: breadth vs precision
The focus guidance did exactly what it said — and that was both its win and its loss:
- **Win (precision):** fewest fabrications of all versions (0.29), rescued the depth-sensitive
  PRs where v2 collapsed (quarkus#28314 1→8, accumulo 0→3, tycho 1→4), tied v1 at 2/3 cost.
- **Loss (breadth):** "smallest investigation that answers the question" suppressed the
  survey of adjacent issues: −0.8 goods/PR and +0.35 misses/PR vs v2 across the full mix.
  The point metric (+1/good, −1/miss) prices breadth; v2's unfocused wandering accidentally
  harvested it.

Generation-failure holes (excluded): v3 netty#15399 (85-char review), v2 quarkus#34681 and
wildfly#6304 (empty reviews) — infrastructure, not judging.

## v4 recommendation
1. **Keep** the verify-impact half: "for a changed/removed symbol, check who calls or
   imports it" (it produced the precision gains).
2. **Drop/replace** the wrap-up-early half. New framing: verify impact AND keep surveying —
   "after confirming the asked question, note any adjacent issues you encountered; a finding
   list that covers the whole change is more useful than a narrow one."
3. **Path normalization** in file_editor/glob/grep (accept repo-relative like `search`) —
   62% of sessions flail on path formats, 11% of all turns.
4. **PR-added-file manifest** in the subagent injection ("files added by this PR are NOT on
   disk; read them from the diff") — 32% of sessions burn turns hunting them.

v4 hypothesis: v2's breadth + v3's precision at v3's cost.
