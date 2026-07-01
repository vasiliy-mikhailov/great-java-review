# Fix Java Bugs — find real Java bugs, prove them with a test, fix them

An agentic pipeline that reads large Java projects **file by file**, finds **real
bugs**, proves each one with a **failing unit test**, **fixes** the root cause,
and presents the find+fix upstream as ordinary human work. The model under the
harness is the **Qwen-3.6-27B-FP8** endpoint; the grader is Claude.

> **The product is a portable skill.** The file-level unit — find → prove → fix
> the bugs in ONE Java file — ships as a standalone, no-runtime Agent Skill any
> coding agent can follow: **[`vasiliy-mikhailov/fix-java-bugs-skill`](https://github.com/vasiliy-mikhailov/fix-java-bugs-skill)**
> (source in [`skills/fix-java-bugs/`](skills/fix-java-bugs/SKILL.md)). Everything
> else in this repo exists to *forge and score* that skill, not to be shipped.

## The pipeline: repo → module → file (suspect → reproduce → fix → synthesize)

A deterministic **registry pipeline** (`src/current_version/suspicion.py`). The
harness opens a repo and **descends repo → module → file**: it lists the modules
and, within each, iterates the source files, applying the **fix-java-bugs skill
to every file**. Coverage is therefore *structural* — every file is read, not
sampled. Each file is one find → prove → fix unit, realized by three agents that
write a shared registry of **Suspicion → Bug → Solution**:

```
    repo ─▶ module ─▶ file   (one investigator per source file)
 ┌──────────────┐   ┌───────────────┐   ┌────────────┐   ┌──────────────┐
 │  SUSPECTOR   │──>│  REPRODUCER   │──>│   SOLVER   │──>│ SYNTHESIZER  │
 │ read 1 file  │   │ prove w/ test │   │  fix prod  │   │  emit review │
 └──────────────┘   └───────────────┘   └────────────┘   └──────────────┘
   Suspicions          Bugs                Solutions          PR / review
```

- **Suspector** → *Suspicions.* Seeded at ONE file (its "entrance point"), reads
  it in full and explores outward as a bug needs; fires on sight — a Suspicion =
  `{observation, suspected_bug, location, confidence}`. **Confidence is the only
  priority signal.** Whole-repo is the only mode (the old diff-anchored
  `INVESTIGATE_MODE` was removed); coverage is guaranteed by the driver handing
  out every file, so there is **no coverage reward** — the per-file reward is just
  `Σ confidence over confirmed`. A dedup subagent merges overlapping entries.
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
- **Synthesizer** → reads the registry and emits the PR material: each Bug with
  its test and (when present) its verified fix; `inconclusive` suspicions become
  hedged open questions.

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
untrusted code **only ever inside a container**. The JDK is picked by the
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

The reproducer/solver rewards take a `base · 0.9^(badness)` shape (full credit
for a real result, discounted for a bigger-than-needed proof/fix). Coverage
needs no reward: the repo → module → file descent reads every file by
construction — a *capacity* limit solved by architecture, not reward-shaping
(`AGENTS.md` P13/P19).

## Measurement: Claude is the judge

Quality numbers come from **Claude, never the reviewer model** (a model that
self-grades certifies its own fabrications). The metric is a code-grounded
**point judge** with repo access: per finding good `+1` / critical `+2` /
wrong `−1` / trivial `0`, minus `−1` per missed human∪Claude point. The
benchmark is a 200-PR set run **whole-repo**: recall is whether the whole-repo
descent surfaces each PR's known bug (location match) — a harder, more honest
number than diff review.

## The upstream experiment

The claim under test is that **AI-found-AND-fixed** bugs land on their merits
when presented as ordinary human work. So every upstream PR is built from
**Qwen's** registry entries first — its suspicion, its regression test, its
`fix_diff` — proven red→green by execution before opening. The agent substitutes
its own test/fix only when Qwen's is genuinely bad, and only after explicit human
acceptance. PRs are spread across maintainers and never go to `apache/*` without
an explicit go (`AGENTS.md` P5/P17). As of 2026-07 the experiment has produced
merged bug-fix PRs across multiple projects (e.g. gson, RxJava, zxing, hutool,
selenium), several landed by project leads.

## Layout
- `src/current_version/suspicion.py`  the registry pipeline (all four agents + tools; `run_suspicion_review` is the repo→module→file descent)
- `skills/fix-java-bugs/`  **the shipped product** — the portable find→prove→fix Agent Skill (+ `detect-java-version`, `detect-unit-testing-framework`)
- `head_worker.sh` / `head_watchdog.sh` / `explore_daemons.sh`  the lane loop, self-healing watchdog, queue-refill daemons. **Lane count is a runtime knob** — `echo N > head_lanes.max` scales the fleet up or down live (the watchdog converges each cycle)
- `docker/`  `Dockerfile` (`review-harness`) + `run.sh` (mounts the live tree into the container)
- `build_bug_corpus.py`  benchmark dataset builder from real bug-fix PRs
- **Benchmark oracle:** `excellent_reviews.json` (frozen human-review corpus) +
  `src/dataset.py`, `src/metric.py`, `src/llm_client.py` (shared infra the pipeline imports)

## Run

The pipeline runs inside the `review-harness` container against one repo (the
whole-repo descent — no mode flag):

```bash
HARNESS_NAME=h-myrun \
  docker/run.sh python -u src/current_version/suspicion.py <owner>/<repo> head
# continuous multi-lane crawl (queue-driven, resumable, self-healing):
echo 4 > head_lanes.max          # target lane count (change any time, no restart)
./head_watchdog.sh &             # converges lanes to head_lanes.max + refills/prunes
./explore_daemons.sh refill &    # keeps head_queue.txt topped up
```

## Notes
- GitHub auth comes from the `gh` CLI keyring at runtime — **no token stored**.
- **Exactly one GitHub worker at a time**; rate-limit-aware, backoff on secondary limits (`AGENTS.md` P5).
- Qwen creds via `.env` (`QWEN_API_KEY`/`QWEN_BASE_URL`), never committed; **reasoning ON**, full 131072 window.
- The harness Python and repo tree are **mounted**, not baked — a host edit is the whole deploy (no rebuild).
- `AGENTS.md` is the authoritative contract (P1–P19); this README is the orientation.
