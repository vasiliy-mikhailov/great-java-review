# Prompt comparison (qwen)

Mean review-mimicry score on held-out PRs (higher = closer to the real reviewer). Metric = 0.85·LLM-judge + 0.15·lexical.

| Reviewer | n | baseline | per-reviewer GEPA | single GEPA |
|---|---|---|---|---|
| franz1981 | 12 | 0.302 | 0.285 | 0.256 |
| snuyanzin | 12 | 0.251 | 0.215 | 0.223 |
| laeubi | 12 | 0.338 | 0.380 | 0.340 |
| dmlloyd | 12 | 0.244 | 0.256 | 0.242 |
| mickaelistria | 12 | 0.219 | 0.263 | 0.241 |
| lhotari | 12 | 0.272 | 0.288 | 0.286 |
| HeikoKlare | 12 | 0.281 | 0.312 | 0.319 |
| wilkinsona | 12 | 0.240 | 0.223 | 0.245 |
| vietj | 12 | 0.274 | 0.285 | 0.260 |
| SaptarshiSarkar12 | 12 | 0.202 | 0.205 | 0.219 |

| **MEAN** |  | **0.262** | **0.271** | **0.263** |

## Takeaway

- Per-reviewer GEPA vs baseline: +0.009
- Single universal GEPA vs baseline: +0.001
- Per-reviewer vs single: +0.008 (positive = personalization helps)