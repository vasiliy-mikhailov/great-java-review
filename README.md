# Great Java Review — find real Java bugs, prove them with a test, fix them

An agentic pipeline that mines large Java projects for **real bugs**, proves each
one with a **failing unit test**, **fixes** it, and presents the find+fix
upstream as ordinary human work. The model under the harness is the
**Qwen-3.6-27B-FP8** endpoint; the grader and curator is Claude.

> **Note.** A frozen corpus of real human code-review comments
> (`excellent_reviews.json`) serves as the **benchmark oracle** the pipeline's
> findings are scored against (`AGENTS.md` P5/P18) — the only role human reviews
> play here.

## The pipeline: suspect → reproduce → fix → synthesize

A deterministic **registry pipeline** (`src/current_version/suspicion.py`). Each
stage is a separate agent given only the tools and the single reward its job
needs; nothing is parsed from prose — every artifact is stored through a tool.
The registry holds three linked entry types, **Suspicion → Bug → Solution**:

```
                          src/current_version/suspicion.py
 ┌──────────────┐   ┌───────────────┐   ┌────────────┐   ┌──────────────┐
 │  SUSPECTOR   │──>│  REPRODUCER   │──>│   SOLVER   │──>│ SYNTHESIZER  │
 │ investigate  │   │ prove w/ test │   │  fix prod  │   │  emit review │
 └──────────────┘   └───────────────┘   └────────────┘   └──────────────┘
   Suspicions          Bugs                Solutions          PR / review
```

- **Suspector** → *Suspicions.* Sweeps for likely bugs and fires on sight; a
  Suspicion = `{observation, suspected_bug, location, confidence}`. **Confidence
  is the only priority signal.** Two modes (`INVESTIGATE_MODE`): `mr` reads just
  the PR diff (the **benchmark path** — the human-review oracle is diff-scoped),
  `repo` sweeps the whole repo biased toward *tested* modules (the **RLVR path** —
  execution is the oracle). A dedup subagent merges overlapping entries on the way in.
- **Reproducer** → *Bugs.* Takes the highest-confidence suspicion and must **show
  the bug with a unit test** in a per-JDK sandbox — a JUnit `@Test` that fails on
  the bug (`regression_test` > `test` > `log` > `grep`). Coupled code is reached
  by *mocking collaborators* (never copying the class under test). A test-critic
  checks the assertion is the genuinely-correct behaviour (Javadoc/JLS/round-trip
  contract), not a convenient one. A verdict shown by a run, or it's `inconclusive`.
- **Solver** → *Solutions.* Only on a Bug that carries a test. It re-materializes
  the test into a clean tree and edits *production* code until green. Green ≠
  correct: it first reasons what the code *should* do, then makes that the fix.
  Reward `R_solve = passes · 0.9^(lines_changed) · test_untouched` favours the
  smallest production change that leaves the test untouched.
- **Synthesizer** → reads the registry and emits the review / PR material: each
  Bug with its test and (when present) its verified fix; `inconclusive`
  suspicions become hedged open questions.

**No-cheat is structural, not a guard.** The reproducer/solver only get
`run_java`, `edit_file` (str-replace on an *existing* file), and `create_test`
(a *new* file only under `src/test/**`). There is no tool with which to stub or
copy the class under test, and the sandbox wipes any stray new `.java`. The
reward is bound by the scorer **re-running the genuine code**.

## Verification by execution (the sandbox)

Text tools cannot settle our worst errors (wrong overload, comparator contract,
NPE, "won't compile", external-API behaviour). The compiler/runtime is the exact
oracle. Builds run on a remote Docker host (server2): per-JDK sandbox images
`review-java-{8,11,17,21,25,26}-sandbox`, dependencies through a **Nexus** proxy,
untrusted PR code **only ever inside a container**. The JDK is picked by the
project's **build floor, detected by compiling** — not the declared
`maven.compiler.*`, since a wrong JDK yields false errors that poison a verdict.

## How it's trained: RLVR, no caps

The per-rollout reward is **execution-grounded** — the test really fails before
the fix and passes after; a fabrication that survives text-checking dies on a
real `javac`/`mvn` run. Two rules hold throughout (see `AGENTS.md` P2/P10/P17):

- **No reasoning budget** — no `thinking_token_budget`, no small `max_tokens`.
  A cap doesn't tighten the answer; the model gives up and emits noise.
- **No wall-clock cap on a rollout** — a truncated trajectory has no clean
  reward. Runs are bound only by internal per-step limits + a stall detector.

The Suspector's coverage reward, for example, is
`Σ confidence(confirmed) · 0.9^(unopened source files)` — credit for breadth,
discounted for files never looked at.

## Measurement: Claude is the judge

Quality numbers come from **Claude, never the reviewer model** (a model that
self-grades certifies its own fabrications). The metric is a code-grounded
**point judge** with repo access: per finding good `+1` / critical `+2` /
wrong `−1` / trivial `0`, minus `−1` per missed human∪Claude point. The
benchmark is a 200-PR set run `mode=mr` (the human oracle is diff-scoped),
graded 3-way (`mr` / `mr_code` / `mr_code_tools`) to show whether reading the
repo + running tools actually helps.

## The upstream experiment

The claim under test is that **AI-found-AND-fixed** bugs land on their merits
when presented as ordinary human work. So every upstream PR is built from
**Qwen's** registry entries first — its suspicion, its regression test, its
`fix_diff` — proven red→green by execution before opening. The agent substitutes
its own test/fix only when Qwen's is genuinely bad, and only after explicit human
acceptance. PRs carry **no AI attribution**, are spread across maintainers, and
never go to `apache/*` without an explicit go (`AGENTS.md` P21/P7). As of
2026-06 the experiment has produced merged bug-fix PRs across multiple projects
(e.g. gson, RxJava, zxing, hutool, selenium), several landed by project leads.

## Layout
- `src/current_version/suspicion.py`  the active registry pipeline (all four agents + tools)
- `head_worker.sh` / `head_watchdog.sh` / `explore_daemons.sh`  the lane loop, self-healing watchdog, queue-refill daemons
- `docker/`  `Dockerfile` (`review-harness`) + `run.sh` (mounts the live tree into the container)
- `harvest_candidates.py`  append-only ledger of judged-real PR candidates (`results/pr_candidates.jsonl`)
- `build_bug_corpus.py` / `compare_iters.py`  benchmark dataset builder + iteration comparison
- `skills/`  reusable operator skills (e.g. `detect-java-version`)
- **Benchmark oracle:** `excellent_reviews.json` (frozen human-review corpus) +
  `src/dataset.py` (benchmark units), `src/metric.py`, `src/llm_client.py` (shared infra the pipeline imports)

## Run

The active bug pipeline runs inside the `review-harness` container against one repo:

```bash
HARNESS_NAME=h-myrun INVESTIGATE_MODE=repo \
  docker/run.sh python -u src/current_version/suspicion.py <owner>/<repo> head
# continuous multi-lane crawl (queue-driven, resumable, self-healing):
./head_worker.sh        # one lane; run several + ./head_watchdog.sh + ./explore_daemons.sh refill
```

## Notes
- GitHub auth comes from the `gh` CLI keyring at runtime — **no token stored**.
- **Exactly one GitHub worker at a time**; rate-limit-aware, backoff on secondary limits (`AGENTS.md` P7).
- Qwen creds via `.env` (`QWEN_API_KEY`/`QWEN_BASE_URL`), never committed; **reasoning ON**, full 131072 window.
- The harness Python and repo tree are **mounted**, not baked — a host edit is the whole deploy (no rebuild).
- `AGENTS.md` is the authoritative contract (P1–P21); this README is the orientation.
