# Great Java Review — reviewer-style mining + GEPA prompt optimization

Mine GitHub for high-signal Java code reviewers, capture their reviews, then use
**GEPA** (reflective prompt evolution) to discover prompts that make an LLM
review code in each reviewer's voice — and a single universal prompt — evaluated
against the **Qwen-3.6-27B-FP8** endpoint.

## Results (v1)

- **Corpus:** 10 deep reviewers × up to 300 substantive reviews
  (`excellent_reviews.json`) + a ~3k-reviewer wide pool mined free from the
  inline-comment index. Reviewers are real maintainers (DaveCTurner, normanmaurer,
  vietj, franz1981, dmlloyd, …).
- **Prompt comparison** (held-out PRs, mimicry = 0.85·LLM-judge + 0.15·lexical):
  **per-reviewer 0.271 > single 0.263 ≈ baseline 0.262** — personalization gives a
  small edge (7/10 reviewers), one universal prompt buys ~nothing over the generic
  seed. Effect is small + noisy on ~12-PR tests; see `results/comparison_hc.md` for
  the higher-confidence run (60-PR held-out, temp=0).
- **AutoResearch tuning** (`autoresearch.py`, Karpathy-style trajectory-informed
  keep/revert): mimicry on vietj **0.331 → 0.475 (+43%)** over 40 trials, then knob
  saturation. `results/autoresearch_curve.qwen.png`.
- **Output-cap ablation** (`token_sweep.py`): `gen_max_tokens` is a *cap, not a
  target* — score rises until the cap clears the reviewer's natural review length
  (vietj ~120 tok), then is **flat + noise**. Knee ≈ 233; bigger is wasted compute,
  not better. `results/token_sweep_fib.qwen.png`.
- **Leakage guard:** optimized prompts must be self-contained; a guard
  (`leaks_reference` + penalty + seed-fallback) rejects prompts that assume the
  held-out reference review is an input.

See `AGENTS.md` for the problem/delegation model (P1 meta · P2 main: mimicry
prompts · P3 corpus · P4 scaling · P5–P8 substrate · P9 auto-tune).

## Pipeline (all stages resumable, single GitHub worker)

```
run_pipeline.sh
 ├─ 1. crawl.py discover   identify reviewers from inline-review-comment volume
 ├─ 2. crawl.py collect    per reviewer, gather ~300 substantive reviews via
 │                         `reviewed-by:` search -> excellent_reviews.json
 ├─ 3. gepa_run.py per     evolve a per-reviewer mimicry prompt (x10)
 ├─ 4. gepa_run.py single  evolve one universal prompt across all reviewers
 ├─ 5. compare.py          score baseline vs per-reviewer vs single on held-out PRs
 └─ 6. fib_sweep.py        scaling curve: universal-prompt quality vs #reviewers
                           trained on (k = 1,2,3,5,8,... Fibonacci)
```

### Fibonacci scaling result (universal prompt vs. #reviewers, up to ~10k)
`fib_sweep.py` re-runs the single-universal-prompt GEPA optimization on the first
**k** reviewers for each Fibonacci `k` — `1, 2, 3, 5, 8, 13, …, 6765, 10946`
(`max_k` ≈ 10k, capped at however many reviewers are currently in the pool, plus
the full-set point). Each resulting prompt is scored on the **same fixed global
held-out eval set**, so the points form a comparable generalization curve.
Output: `results/fib_sweep.<profile>.json` / `.md` (table + ASCII curve). A rising
curve means a single prompt keeps benefiting from more reviewers; a plateau/decline
means styles conflict and per-reviewer prompts pay off more.

Design that scales to k≈10k cheaply:
- **Wide pool, zero extra API.** Instances are mined straight from the discovery
  comment index (`src/wide_dataset.py`): input = the diff hunks a reviewer
  commented on, reference = their actual inline comments. ~10k reviewers become
  available without any per-review enrichment.
- **Bounded GEPA cost.** `trainset(k)` = one instance per reviewer over the first
  `k` reviewers (size ≈ k, up to thousands); GEPA *samples* it, so cost is capped
  by `metric_budget(k) = base·(1 + α·log₂k)` (capped at `base·3`), **not** by `k`.
- **Comparable points.** A fixed global val set (GEPA candidate selection) and a
  fixed global eval set (the reported curve) are shared across all `k`.
- **Auto-extends.** Reviewers are added best-covered-first; as the progressive
  wide crawl grows the pool past 1597/2584/4181/6765/10946, re-running the sweep
  extends the curve. The run is resumable (cached per `k`).

### Progressive wide crawl (to reach ~10k reviewers)
`crawl.py wide` (see `run_wide.sh`) auto-discovers hundreds of `language:Java`
repos via star-bucketed search and shallowly crawls each into the same
`comments_index.jsonl`, growing the distinct-reviewer pool toward
`github.wide.target_reviewers`. Single worker, resumable, meant to run for hours/
days in the background. The deep track (10 reviewers × 300 reviews) is unaffected.

## Layout
- `src/gh_client.py`   stdlib, rate-limited, single-worker GitHub client (token from `gh`)
- `src/crawl.py`       discovery + collection
- `src/dataset.py`     excellent_reviews.json -> GEPA instances + splits
- `src/llm_client.py`  OpenAI-compatible client (Qwen; model-agnostic)
- `src/metric.py`      review-mimicry metric: 0.85·LLM-judge + 0.15·lexical
- `src/gepa_run.py`    GEPA adapter + per-reviewer / single optimization
- `src/compare.py`     held-out comparison report
- `excellent_reviews.json`  the reproducible dataset (reviewer -> reviews w/ PR, diff, review body, inline comments, ids, urls)
- `prompts/`           optimized prompts (per_reviewer/*.qwen.txt, single_great.qwen.txt)
- `results/`           comparison.json / comparison.md + GEPA run artifacts

## Run
```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./run_pipeline.sh qwen          # full pipeline against the Qwen endpoint
# or individual stages:
./venv/bin/python src/crawl.py discover
./venv/bin/python src/crawl.py collect
./venv/bin/python src/gepa_run.py per --login DaveCTurner --profile qwen
./venv/bin/python src/gepa_run.py single --profile qwen
./venv/bin/python src/compare.py qwen
nohup ./run_wide.sh &                      # progressive wide crawl toward ~10k reviewers
./venv/bin/python src/fib_sweep.py qwen    # Fibonacci scaling curve (auto-extends as pool grows)
```

## Notes
- GitHub auth comes from the `gh` CLI keyring at runtime — no token stored.
- `config.yaml` controls seed repos, selection thresholds, Qwen endpoint, GEPA budget.
- Qwen reasoning is disabled (`enable_thinking: false`) for speed; the prompt does the work.
- Claude as a GEPA *task* model is deferred (Qwen-only for now); the client is
  model-agnostic, so add a `claude` profile + key to extend.
- "10/10 pain points" is operationalized as substantive review units
  (CHANGES_REQUESTED, ≥2 anchored inline comments, or a long written body),
  ranked by a concern-keyword/code-suggestion heuristic and the LLM judge.
