# Fibonacci scaling sweep — universal prompt (qwen, in_domain)

How well ONE universal GEPA prompt mimics the first `k` reviewers, scored on **held-out PRs of those same k reviewers** (in-domain). k follows Fibonacci. The prompt only has to generalize to the reviewers we actually have, not the population.

| k (reviewers) | train | eval PRs | budget | in-domain score | curve |
|---|---|---|---|---|---|
| 1 | 8 | 6 | 89 | 0.3161 | `#################` |

## Takeaway

- k=1 (mimic one reviewer): **0.3161**.
- k=1 (one prompt for all of them): **0.3161**.
- Best at k=1 (0.3161).
- A FALLING curve ⇒ one prompt can mimic a single reviewer well but degrades as it must satisfy more distinct voices at once — i.e. personalization (per-reviewer prompts) is needed. A FLAT/RISING curve ⇒ the reviewers are stylistically compatible and a single prompt captures them all.