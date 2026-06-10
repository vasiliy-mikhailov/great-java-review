# High-confidence prompt comparison (qwen)

Held-out test = 60 PRs/reviewer (disjoint from training), deterministic temp=0 generation. Mean review-mimicry score (0.85·judge + 0.15·lexical).

| Reviewer | n | baseline | per-reviewer | single |
|---|---|---|---|---|
| wilkinsona | 60 | 0.338 | 0.334 | 0.328 |
| HeikoKlare | 60 | 0.348 | 0.327 | 0.339 |
| laeubi | 60 | 0.329 | 0.329 | 0.328 |
| lhotari | 60 | 0.306 | 0.301 | 0.297 |
| dmlloyd | 60 | 0.245 | 0.266 | 0.260 |
| franz1981 | 60 | 0.262 | 0.269 | 0.254 |
| vietj | 60 | 0.294 | 0.327 | 0.274 |
| snuyanzin | 60 | 0.242 | 0.235 | 0.237 |
| mickaelistria | 60 | 0.257 | 0.354 | 0.283 |
| **MEAN** |  | **0.291** | **0.305** | **0.289** |

## Takeaway

- per-reviewer vs baseline: +0.0135 (5/9 reviewers win)
- single vs baseline: -0.0022
- per-reviewer vs single: +0.0157 (7/9 reviewers win)