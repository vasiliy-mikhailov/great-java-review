# AGENTS.md

A delegation protocol, not a checklist. Each entry is a **problem**: one
autonomous concern the operator has offloaded to the agent. Clustered — meta
(P1); recipe/setup (P2–P4); substrate (P5–P10); harness (P11–P15); evaluation (P16).

> **WORKSPACE CONVENTION (operator-set).** ALL work happens in **`current_attempt/`**
> — the single live directory (this is where `src/`, `data/`, `results/`,
> `excellent_reviews.json`, etc. live; `venv` and `.env` are symlinked from the repo
> root, so code runs unchanged with `cwd = current_attempt`). Snapshots are made ON
> REQUEST as **read-only copies** → `attempt_N/`. **Never edit or run inside an
> `attempt_N/` snapshot** — that is what tangles cross-attempt paths/references.
> To snapshot: `cp -r current_attempt attempt_N` (drop the `venv`/`.env` symlinks),
> and it must contain zero references back to other attempts.

---

## P1 — Problem (writing this file): keep AGENTS.md compact and outcome-named.

**Value:** keep AGENTS.md compact and outcome-named.

**Contract and constraints** *(operator-only; the agent does not edit this section)*:
A problem is a self-amplifying attractor — one autonomous concern with a single
extremum (its Reward) and a single trigger (its Attention mechanism) that pulls
the agent's attention and amplifies until satisfied. Each is a concern the
operator has offloaded to the agent, making this file a delegation protocol, not
a checklist. Only one problem is in foreground at a time (Ukhtomsky); before
every action the agent verifies exactly one is dominant — concurrent problems
signal confusion to resolve first. Control passes when a stronger trigger fires
or the current extremum is approached; an interrupted problem is resumed, not
restarted, so each persists enough state for genuine resumption. Problems are
written for an intelligent agent searching a fuzzy environment in Ralph loops:
supply no implementation detail the agent can fill itself, and keep each as short
as possible. Every problem has five sections: Value, Contract and constraints
(operator-only, agent doesn't edit), Solution search approach and hints, Reward
(one extremum read off without judgement), Attention mechanism. Backtick-pinned
concretes are recognition scaffolding and survive trims; aging enumerations get
stripped. The file is clustered — meta (P1); recipe/setup (P2–P4); substrate
(P5–P10); harness (P11–P15); evaluation (P16).

**Solution search approach and hints:** read → why → intent — for each clause ask
"why is this here?". Strip when the answer is mechanism the agent already fills,
a bare plea for the rule, or an aged enumeration; keep when it scopes when the
rule applies, names a recognition concrete, or signals when to revisit.

**Reward:** cuts that lose words without losing the rule or its scope.

**Attention mechanism:** the file is the channel — an operator edit to a problem's
Contract, or a problem's agent-mutable sections visibly bloating, is the signal to
re-audit.

---

## P2 — Problem (mimicry prompts) **[MAIN / apex]**: GEPA-evolved prompts that review like a given reviewer.

**Value:** prompts that make the model produce a reviewer's **high-quality reviews** in their voice — per-reviewer and one universal. We mimic their substantive technical feedback (real pain points), NOT their every comment (LGTM / nits / process chatter are explicitly out of scope). The north-star: P3 (corpus) feeds it, P4 (scaling) questions it, P5–P8 enable it; delete this and nothing else has a reason to run.

**Contract and constraints** *(operator-only)*: GEPA reflective evolution; task + reflection model = the active profile (`qwen` now, model-agnostic via profiles). Produce per-reviewer prompts AND one universal prompt, then a held-out comparison vs the `SEED_SINGLE` baseline. Mimicry metric = `0.85·LLM-judge + 0.15·lexical` vs the real review. **THE POINT TO REACH = the two-human same-PR agreement ceiling ≈ `0.485`** (`results/score_calibration.json`): two human experts reviewing the SAME PR agree only ~0.485 (range 0.22–0.91), so that IS the realistic ceiling, not 1.0. Calibration: floor (any review not addressing THIS PR) ≈ `0.04`; **excellent ≈ `0.48+`**. Current Qwen ≈ `0.29` = **~56% of the way floor→ceiling** — solid engagement, real headroom. Closing the Qwen→ceiling gap is the goal (and is what P10 / Attempt 2 chase).

**Solution search approach and hints:** custom `GEPAAdapter` in `gepa_run.py` (PR→review scored vs reference); GEPA cost is bounded by `max_metric_calls`, not trainset size; inspect any run via `gepa_chart.py <run_dir>`. Score buckets: `<0.05` floor · `0.15–0.30` solid · `0.30–0.48` good · `0.48+` excellent.

**Reward:** best-candidate held-out score, measured against the `0.485` human ceiling (not 1.0).

**Attention mechanism:** a reviewer's dataset reaches usable size, or a seed/metric/budget edit.

---

## P3 — Problem (reviewer corpus): a reproducible dataset of high-signal Java reviewers and their reviews.

**Value:** capture enough substantive reviews per great Java reviewer to learn their style, reproducibly — the input P2 consumes.

**Contract and constraints** *(operator-only)*: ONLY high-quality reviews are kept — in BOTH tracks. The goal is to mimic a reviewer's SUBSTANTIVE technical feedback, not their every comment; LGTM / nits / style bikeshedding / process chatter are out of scope and must be dropped. Quality gate = two stages: (1) heuristic floor — `crawl.is_substantive_unit` (`CHANGES_REQUESTED`, ≥ `min_inline_comments` anchored comments, or a comment ≥ `min_body_chars`) and reference ≥ `min_ref_chars`; then (2) a **Qwen rubric judge** (`quality_judge.py`) that keeps only units it rates ≥ `quality_threshold` as concrete, actionable technical review (correctness / concurrency / API / security / tests / design), judged from the diff + the reviewer's comments, cached in `data/cache/quality.jsonl`. Applies to the wide pool (`wide_dataset.build_wide_instances`, `quality_gate`) and the deep pool. **DROP REVIEWS, NOT REVIEWERS — and rubric-score EVERY review, not a sample.** Data quality is king. The task is to mimic high-quality *reviews*, not a reviewer's every comment, so keep ALL maintainers but keep only each one's substantive (rubric≥`quality_threshold`) reviews. Deep corpus is ~53% substantive (`2981/5607`, dist `{1:875,2:877,3:874,4:1746,5:1235}`); every maintainer retains substantive reviews (15–193 each) — drop the chatter, keep the maintainer. A FRONT-OF-LIST SAMPLE LIES: `dmlloyd` looked 25% substantive in his first 8 reviews but is 57% (`171/300`) over all of them — so score EVERY review (`quality_judge deep`, cached in `data/cache/quality.jsonl`), never extrapolate from a sample. Never select by a lightweight inline-count heuristic either: the PoC `agent_poc_batch.pick()` (2–6 anchored comments) leaked 3/5 chatter targets (radcortez#1277 "+1"=1; romani#1075 bare questions=1; Saptarshi nits=3). GEPA train/eval draws substantive reviews diversely across maintainers from the curated pool via `gepa_oh.gated_materialize`. **SECOND JUDGE from a DIFFERENT model family — mandatory, to break the Qwen monoculture:** one LLM gate silently passes off-language and process content, so curate with an independent judge too. Here that is Claude via Claude Code subagents (no Anthropic key on this box): shard the corpus (`data/cache/claude_judge/shard_*.jsonl`), fan out one judge subagent per shard → `*.verdict.jsonl`, combine. Findings that justify it: the two judges **agree only ~75% (disagree ~25% of `5607`)** — a single judge is NOT ground truth; and Claude (language/file-aware) drops what Qwen kept — NON-Java reviews (Kotlin/JS/TS/Scala: `JetBrains/intellij-community`→0 technical, `square/okhttp`/`swankjesse` 257→2, `Aiven-Open/klaw`=JS/TS) plus build/CI/config files and process chatter. The "Java corpus" is heavily polyglot; only a language-aware judge catches it. Curated pools: Qwen≥4=`2981`, Claude-technical=`2781`, **BOTH-agree=`2173` = the gold GEPA source** (`data/cache/clean_both_technical.json`); prefer the dual-judged intersection. ACCEPTED tradeoff (operator-approved): Qwen is also the task model and the metric judge, so Qwen-selecting-the-corpus risks selection bias toward Qwen's own taste; disclosed and accepted. Deep track = `selection.num_reviewers` reviewers × `reviews_per_reviewer` (`300`) such reviews → `excellent_reviews.json` (repo, PR id/title/body/diff, reviewer id, review id, review body, inline comments, urls). Wide track = as many reviewers as reachable (toward `wide.target_reviewers`), mined free from the discovery index, for the scaling sweep.

**Solution search approach and hints:** discovery streams `/repos/{repo}/pulls/comments` → `comments_index.jsonl`, grouped into review units by `pull_request_review_id`. Reuse what's already crawled before fetching. Recognition: real maintainers (`DaveCTurner`, `normanmaurer`, `vietj`, `franz1981`).

**Reward:** chosen reviewers at their review target with full records on disk.

**Attention mechanism:** a chosen reviewer below target, or an edit to selection thresholds/targets.

---

## P4 — Problem (scaling curve): does ONE universal prompt suffice as the reviewer set grows?

**Value:** how well a single prompt mimics the first `k` reviewers, `k` over Fibonacci (`1,2,3,5,8,…` to `max_k`).

**Contract and constraints** *(operator-only)*: IN-DOMAIN only (`eval_mode: in_domain`) — score each `k`'s prompt on held-out PRs of the SAME `k` reviewers; it must generalize to the reviewers we have, NOT the population. Reviewers added best-covered-first (`k=1 ⊂ k=2 ⊂ …`); cost bounded (round-robin `val_cap`/`eval_cap`, budget ~log k). Curve auto-extends as the pool grows.

**Solution search approach and hints:** `fib_sweep.py` → `fib_chart.py`. Reading: falling curve ⇒ personalization (P2 per-reviewer) needed; flat/rising ⇒ one prompt captures them all.

**Reward:** in-domain score per `k`, read off the curve.

**Attention mechanism:** pool grew past the next Fibonacci value, or an eval_mode/split/cap edit.

---

## P5 — Problem (GitHub politeness): never get the token banned.

**Value:** harvest GitHub at scale without tripping rate-limit/abuse bans.

**Contract and constraints** *(operator-only)*: exactly ONE GitHub worker at any instant (no parallel git/crawl, ever); honor primary + secondary limits; token from the `gh` keyring at runtime, never on disk.

**Solution search approach and hints:** one rate-aware client `gh_client.py`. Serialize the two GitHub jobs (wide `crawl` vs deep `collect`) — they must never overlap.

**Reward:** zero abuse responses; budget never exhausted by overlap.

**Attention mechanism:** a `403/429` or `low budget` log line, or two GitHub processes alive at once.

---

## P6 — Problem (job durability): long jobs survive interruption and resume.

**Value:** multi-hour crawls and sweeps reach completion across kills.

**Contract and constraints** *(operator-only)*: launch detached (`nohup`), NOT as harness-tracked tasks — those get reaped; every stage resumable from on-disk state; checkpoint often.

**Solution search approach and hints:** resumable caches (`discovery_state.json`, partial `excellent_reviews.json`, per-`k` sweep json). A `killed`/`stopped` status ⇒ relaunch detached, never restart from zero.

**Reward:** a killed job resumes with no lost work.

**Attention mechanism:** a job dies, or a stage has no resume checkpoint.

---

## P7 — Problem (dependency isolation): no dependency hell.

**Value:** the pipeline installs and runs reproducibly.

**Contract and constraints** *(operator-only)*: use a `venv`; the crawler stays stdlib-only (zero install risk); heavier deps (`gepa`, `openai`, `matplotlib`) live only in the venv (`requirements.txt`).

**Solution search approach and hints:** verify each import on the target Python before depending on it.

**Reward:** clean import of every used package in the venv.

**Attention mechanism:** an import error, or a newly added dependency.

---

## P8 — Problem (Qwen endpoint): the model under optimization is reachable and bounded-cost.

**Value:** GEPA task + reflection calls hit Qwen reliably within budget.

**Contract and constraints** *(operator-only)*: OpenAI-compatible `llm_client.py`; key from `.env` (`QWEN_API_KEY`, never committed); Qwen may run concurrently (`qwen.max_concurrency`) — it is NOT the single GitHub worker. Qwen runs with **reasoning ON** (`enable_thinking: true`) for ALL calls — generation, reflection, the metric judge, and the quality judge — because Qwen is markedly weaker without thinking. **Never cap reasoning tokens:** the endpoint context is 128k, so `max_tokens` defaults to a generous `32768` and per-call `max_tokens` overrides are removed (the model stops naturally; the client strips `<think>…</think>`). A small `max_tokens` truncates the reasoning and yields garbage — so don't set one. Slower than no-think, accepted for quality; lean on `max_concurrency` for throughput.

**Solution search approach and hints:** bound spend via GEPA `max_metric_calls` and `fib_sweep` caps.

**Transport (Attempt 3) — the OTHER root cause of `0.0`:** OpenHands runs **non-streaming** by default; litellm hands its scalar `timeout` to httpx as a READ (byte-gap) timeout, but non-streaming withholds every byte until the whole answer is computed → the timeout collapses to "time to compute the entire response" → a long 64k+thinking generation gets guillotined mid-flight as if the socket died → retried → recomputed → loops → empty review = `0.0`. **Fix = streaming** (`stream=True`): tokens are a liveness heartbeat, so the read-timeout fires only on a genuinely silent socket. Wiring: OpenHands raises `ValueError("Streaming requires an on_token callback")` if `stream=True` & `on_token is None`; the agent loop passes `on_token=None` EXPLICITLY and the condenser passes it ABSENT, so use a `StreamingLLM(LLM)` subclass overriding `completion`/`acompletion` with an `is None` check (NOT `setdefault`). `num_retries=10` rides out transient drops; `ladder_smoke.py` diagnoses (TTFT/total/STALL). Long jobs run under `caffeinate -dimsu` (a closed lid suspends the process → looks exactly like a transport hang).

**Reward:** endpoint returns 200; per-run cost within budget.

**Attention mechanism:** a non-200 from the endpoint, or runaway call volume.

---

## P9 — Problem (auto-tune): AutoResearch loop that climbs toward the config maximizing mimicry quality.

**Value:** find the hyperparameter combination that maximizes held-out mimicry score for P2 — via a trajectory-informed keep/revert loop, not blind search.

**Contract and constraints** *(operator-only)*: this is Karpathy-style AutoResearch — propose a TARGETED change informed by the trajectory of past trials, run a comparability-budgeted trial (`gepa_seconds`, ~`5 min`), then KEEP if it beats the incumbent baseline else REVERT. Watch the trajectory two ways: cross-trial (hill-climb toward historically-best knob values) and within-trial (stop a flat run early). The budget alone is NOT the mechanism. Tune ONLY quality knobs; HOLD the measurement FIXED — same eval PRs, same `0.85·judge + 0.15·lexical` metric — so the loop can only win by genuinely closer reviews. Tune on one well-covered reviewer (`vietj`); the winner must be validated on others before adoption.

**Solution search approach and hints:** TWO layers. (1) Engine = `src/autoresearch.py` (the bounded inner loop / measurement harness): `propose()` hill-climbs from the incumbent via `per_knob_best` history (with `explore_p` exploration, `warmup` random seeding); each trial is `gepa.optimize` under `CompositeStopper(TimeoutStopCondition, NoImprovementStopper, any)`; knobs = `reflect_minibatch`, `train_per_reviewer`, `val_size`, generation `max_tokens`/`temperature`, `reflect_think`, `sel_strategy`, `gepa_seed`; resumable via `results/autoresearch.jsonl` (rows carry `rationale`/`kept`), watch `results/autoresearch_curve.<profile>.png`. (2) Outer loop = the `autoresearch` **skill** (`.claude/skills/autoresearch/`): the AGENT supplies what code can't — hypotheses beyond the knob grid. Findings (Karpathy AutoResearch, Mar 2026, shipped as `program.md`): the mechanism is *informed hypothesis from the trajectory → comparability-budgeted trial → keep/revert*, NOT the budget; and the signature escalation is **knobs first, then pivot to editing code/prompt seeds** (`SEED_SINGLE`, the adapter feedback) once knobs saturate — that pivot is the skill's job, not the engine's.

**Reward:** best held-out mimicry score found across trials.

**Attention mechanism:** a trial beats best-so-far, knobs saturate (stalled best ⇒ pivot to code), or the search space / objective changes.

---

## P10 — Problem (context beyond the MR): what data do two AGREEING humans both use?

**Value:** identify the data — beyond the MR diff — that two human reviewers both draw on when they **agree** on a review, so the agent can be given that context and close the Qwen→ceiling gap (P2: 0.29 → ~0.485).

**Contract and constraints** *(operator-only)*: the calibration (`results/score_calibration.json`) shows two humans on the SAME PR agree only ~`0.485`, BUT some pairs hit `0.6–0.91` (high agreement) while others sit at `0.22` (divergence). Convergence is the signal: when two experts independently raise the SAME point, that point is determined by **shared context the MR diff does not contain** — issue-tracker links, the broader codebase (files outside the diff), project conventions / style guides, prior PR & design discussion (e.g. Zulip), commit history, the contract of touched APIs. Catalog those sources, ranked by how strongly they drive agreement. This DEFINES the tool/context set the Attempt-2 agent must read; the MR alone is necessary-but-insufficient (proven: whole-MR only got +~10% over chunks, and is still ~56% of ceiling).

**Solution search approach and hints:** mine high-agreement same-PR human pairs (samePR score ≥ ~0.6 from the `crawl._review_units` index, e.g. `quarkusio/quarkus#52229` metacosm vs gsmet = 0.91); read both reviewers' comments and tag every reference to non-diff data (file paths outside the diff, `#issue`/PR links, "as we discussed", convention names, API contracts). Contrast with low-agreement pairs (what context was MISSING). Output a ranked catalog → the Attempt-2 agent tool set (`read_file`/`grep` the repo, fetch the PR conversation/linked issues).

**Reward:** a ranked catalog of non-MR context sources that correlate with two-human agreement.

**Attention mechanism:** the Qwen-vs-`0.485`-ceiling gap; a new context source found in an agreeing pair; Attempt-2 agent tool design (P11).

---

## P11 — Problem (harness): the loop that lets Qwen read the repo to review.

**Value:** a controllable agent loop that feeds the model the non-MR context (codebase, conventions, API contracts) and whose POLICY P2's GEPA can optimize, so mimicry climbs past the whole-MR plateau toward the `0.485` ceiling. The substrate P10's catalog runs on. **This problem is the assembled machine; its subsystems are P12 (runtime) / P13 (tools) / P14 (compaction) / P15 (topology), and P16 evaluates it.** Single-responsibility: a fix that changes for a runtime/tool/compaction/topology reason lives in that subsystem, not here.

**Contract and constraints** *(operator-only)*: the harness is the **OpenHands V1 Software Agent SDK** (`pip openhands-sdk` + `openhands-tools`, repo `OpenHands/agent-sdk`) — NOT the heavy Docker-first monorepo (`openhands-ai`), which was correctly rejected. The genome/loop contract: (1) per-rollout system-prompt override = the GEPA genome; (2) score the FINAL review only (with thinking-answer extraction); (3) extract the tool-call trajectory for GEPA reflection; (4) point at the thinking-Qwen endpoint (P8); (5) read-only repo at the PR base commit; (6) think on; (7) Python ≥3.12 in a separate `venv-oh` (the 3.14 working venv stays untouched); pin SDK versions (V1 is young, fields churn). The home-grown harness (`agent_review.py` + `gepa_agent.py`) is retained as the BASELINE OpenHands must beat, not deleted. Validation is harness-agnostic: a synthetic planted-defect known-answer set is the acceptance test for whatever harness runs.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P11 (harness); the Contract above is binding.

**Reward:** a repo-reading review that beats diff-only consistently (not just low-base cases), with the policy GEPA-tunable.

**Attention mechanism:** agent+repo Δ over diff-only going negative on high-base reviews; a tool the P10 catalog needs but the loop lacks; any one subsystem problem (P12–P15) visibly dominant.

---

## P12 — Problem (runtime): the harness's execution substrate — reproducible, isolated, right-JDK-per-project.

**Value:** a substrate where the agent (now: its tools) can build, run, and test the repos — so future reality-check tools can verify a mechanical hypothesis against execution instead of imagining it, without poisoning the signal or contaminating the host.

**Contract and constraints** *(operator-only)*: **the whole harness runs INSIDE a Docker container** (operator decision, v8) — `docker/Dockerfile` (python 3.12 + openhands-sdk/-tools + git + ripgrep + JDK + maven), built as image `java-review-v8`, launched via `docker/run.sh`. The repo tree (`current_attempt/`, incl. `data/repos` and `results/`) is **mounted** (5.3G of checkouts — never baked); Qwen creds pass via `-e QWEN_API_KEY/QWEN_BASE_URL`; the Qwen endpoint is reached over the container network. The reality-check `verify` tool (P13) then runs `mvnw`/`gradlew` **natively in this same container** — no docker-in-docker. **Untrusted PR code only ever executes inside this container, never on the host.** Dependency caches are **named volumes** (`oh-m2-cache`/`oh-gradle-cache`), warm across PRs; a per-project JDK so a wrong JDK never yields a FALSE compile error that would poison the judge signal. The single-network-worker rule (P5) still applies to in-container fetches.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P12 (runtime); the Contract above is binding.

**Reward:** any sampled repo builds/tests in a clean container with the correct JDK and a warm cache, host uncontaminated.

**Attention mechanism:** a wrong-JDK false failure; a cold-cache blowup; PR test code about to execute on the host; the run becoming CPU-bound (→ request the offered server).

---

## P13 — Problem (tools): the tool layer the agent calls — correct, contract-faithful, single-call-useful, no-PTY.

**Value:** the tools through which the agent perceives the change and explores the repo; each must do exactly what its description says, in one call, without allocating a PTY.

**Contract and constraints** *(operator-only; DRAFT — review)*: subagents use `grep`/`glob`/`file_editor` (+`search`, +`pr_files`/`pr_file_diff`), **NEVER `terminal`** — both tmux and subprocess backends allocate PTYs → `out of pty devices`/`fork failed` at scale → subagent fails → review `0.0`. Every registered tool's prompt reference MUST match its registered name. `register_tool` idempotent (`register_*_if_absent` + a process guard) or the 2nd rollout errors and all score 0. Read-only: register no write tools.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P13 (tools); the Contract above is binding.

**Reward:** every registered tool does what its description says in one call; zero hallucinated-tool errors.

**Attention mechanism:** a `Tool 'X' not found`; `out of pty devices`/`fork failed`; a non-idempotent register; a tool returning truncated or misleading output.

---

## P14 — Problem (compaction): context stays BOUNDED and COHERENT across a multi-turn review.

**Value:** the agent never blows the 128k window nor loses the thread to a garbled summary — so a long investigation still synthesizes a coherent review.

**Contract and constraints** *(operator-only; DRAFT — review)*: token-based compaction (`LLMSummarizingCondenser`). `keep_first` MUST cover the PR message (it is user-message idx 1; `keep_first=6`) or it gets summarized away and the orchestrator synthesizes blind. **INVARIANT:** `condenser.max_tokens + agent.max_output_tokens ≤ max-model-len` — vLLM ERRORS if `prompt + requested_output > 262144`; with output `131072` the ceiling is `131072`, so `condenser.max_tokens=120000` (token trigger; `max_size=240` is a harmless event-count backstop). The condenser LLM is cloned with `enable_thinking=False`. Tie `condenser.max_tokens` to `max_output_tokens`: change one, move the other.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P14 (compaction); the Contract above is binding.

**Reward:** history never crosses budget; each summary shrinks context and stays factual.

**Attention mechanism:** a summary opening `"Here's a thinking process:"` or larger than the events it replaced; context crossing the threshold; a vLLM `prompt + output > model-len` error.

---

## P15 — Problem (topology): orchestrator / subagent / sub-subagent — the cheapest delegation tree that still fully reviews.

**Value:** the orchestrator decides what to investigate and synthesizes; subagents acquire the surrounding (non-MR) context. The structure must buy real depth without paying for over-exploration.

**Contract and constraints** *(operator-only)*: the orchestrator has **NO file tools** — the diff AND the changed-file context are injected into its first user message, so it reviews the changed files DIRECTLY and delegates ONLY for SURROUNDING/non-MR code (callers, conventions, impls elsewhere). Delegation is depth-2, **sequential** (orchestrator → `investigator` [+`task_tool_set`] → `code-explorer` leaf); the `task` tool is blocking, `tool_concurrency_limit=1`, `MAX_ORCH_STEPS=24`. Subagents MUST get the diff (repo is at BASE; added code is not on disk). The deliverable is the LAST `<review>…</review>` block (combine the finish action's `thought` then `message`, take `ms[-1]`).

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P15 (topology); the Contract above is binding.

**Reward:** the smallest investigation that fully answers and self-terminates and emits a clean extractable review — beating diff-only without cratering.

**Attention mechanism:** never self-terminating (8/8 steps); delegation count climbing (over-delegation → slower + more stalls); the same file read many× across subagents; an empty/garbled review (synthesis stall = `0.0`, NOT a real 0 — a same-PR review is never empty); depth-2 not firing.

---

## P16 — Problem (measurement): a trustworthy per-review score with its evidence on disk.

**Value:** know whether reading the repo helps and at what cost — the evaluation capability P2's optimization and P11's comparison both rely on. Clusters with the eval concern (P2), numbered here because it scores the harness.

**Contract and constraints** *(operator-only)*: **the judge is CLAUDE, never the reviewer model** — a model grading its own reviews shares its blind spots (Qwen self-judging certified its own fabrications: `sevntu#645` Qwen +9 vs Claude −13). Comparison is **3-WAY**: `mr` (diff only) / `mr_code` (diff + full changed files, no tools) / `mr_code_tools` (+ tools + delegation) — so `mr→mr_code` measures "do the full files help?" and `mr_code→mr_code_tools` measures "does exploring the rest of the repo help?". Metric = code-grounded **POINT judge**: per finding good `+1` / critical `+2` / wrong `−1` (verify against the code first) / trivial `0` (praise/restating = 0), minus `−1` per missed human∪Claude point; the judge MUST have repo access (a text-only judge always returns `wrong=0` and misses fabrications). Blind own-review FIRST. When the measurement protocol changes, RE-MEASURE the whole `n` fresh, don't backfill. Qwen-judged numbers are cost-telemetry only.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P16 (measurement); the Contract above is binding.

**Reward:** a per-PR net score you can trust, with its trace on disk.

**Attention mechanism:** the measurement protocol changes (token capture, judge, rubric); a `judge=None` hole; the metric misranks a verified-find review; a Qwen-judged number about to be used as a quality claim.
