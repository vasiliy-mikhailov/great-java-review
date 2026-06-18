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

**Contract and constraints** *(operator-only)*: ONLY high-quality reviews are kept — in BOTH tracks. **High-quality means high-TECHNICAL-content AND non-obvious: a finding a strong reviewer (Claude, reviewing the diff blind) would MISS, yet AGREES is correct once shown — it teaches something the diff does not make obvious. Mere correctness, a keyword match, or restating the diff does NOT qualify; the bar is agreed, non-trivial technical insight (the "Claude-missed-but-agrees" depth score). Validated empirically when curating the test-review eval set: each candidate is Claude-analyzed (own blind read first, then count the human's non-obvious correct findings) and ranked by that depth — `results/test_pick/ranked.json`, selector `src/sample_tests.py`.** The goal is to mimic a reviewer's SUBSTANTIVE technical feedback, not their every comment; LGTM / nits / style bikeshedding / process chatter are out of scope and must be dropped. Quality gate = two stages: (1) heuristic floor — `crawl.is_substantive_unit` (`CHANGES_REQUESTED`, ≥ `min_inline_comments` anchored comments, or a comment ≥ `min_body_chars`) and reference ≥ `min_ref_chars`; then (2) a **Qwen rubric judge** (`quality_judge.py`) that keeps only units it rates ≥ `quality_threshold` as concrete, actionable technical review (correctness / concurrency / API / security / tests / design), judged from the diff + the reviewer's comments, cached in `data/cache/quality.jsonl`. Applies to the wide pool (`wide_dataset.build_wide_instances`, `quality_gate`) and the deep pool. **DROP REVIEWS, NOT REVIEWERS — and rubric-score EVERY review, not a sample.** Data quality is king. The task is to mimic high-quality *reviews*, not a reviewer's every comment, so keep ALL maintainers but keep only each one's substantive (rubric≥`quality_threshold`) reviews. Deep corpus is ~53% substantive (`2981/5607`, dist `{1:875,2:877,3:874,4:1746,5:1235}`); every maintainer retains substantive reviews (15–193 each) — drop the chatter, keep the maintainer. A FRONT-OF-LIST SAMPLE LIES: `dmlloyd` looked 25% substantive in his first 8 reviews but is 57% (`171/300`) over all of them — so score EVERY review (`quality_judge deep`, cached in `data/cache/quality.jsonl`), never extrapolate from a sample. Never select by a lightweight inline-count heuristic either: the PoC `agent_poc_batch.pick()` (2–6 anchored comments) leaked 3/5 chatter targets (radcortez#1277 "+1"=1; romani#1075 bare questions=1; Saptarshi nits=3). GEPA train/eval draws substantive reviews diversely across maintainers from the curated pool via `gepa_oh.gated_materialize`. **SECOND JUDGE from a DIFFERENT model family — mandatory, to break the Qwen monoculture:** one LLM gate silently passes off-language and process content, so curate with an independent judge too. Here that is Claude via Claude Code subagents (no Anthropic key on this box): shard the corpus (`data/cache/claude_judge/shard_*.jsonl`), fan out one judge subagent per shard → `*.verdict.jsonl`, combine. Findings that justify it: the two judges **agree only ~75% (disagree ~25% of `5607`)** — a single judge is NOT ground truth; and Claude (language/file-aware) drops what Qwen kept — NON-Java reviews (Kotlin/JS/TS/Scala: `JetBrains/intellij-community`→0 technical, `square/okhttp`/`swankjesse` 257→2, `Aiven-Open/klaw`=JS/TS) plus build/CI/config files and process chatter. The "Java corpus" is heavily polyglot; only a language-aware judge catches it. Curated pools: Qwen≥4=`2981`, Claude-technical=`2781`, **BOTH-agree=`2173` = the gold GEPA source** (`data/cache/clean_both_technical.json`); prefer the dual-judged intersection. ACCEPTED tradeoff (operator-approved): Qwen is also the task model and the metric judge, so Qwen-selecting-the-corpus risks selection bias toward Qwen's own taste; disclosed and accepted. Deep track = `selection.num_reviewers` reviewers × `reviews_per_reviewer` (`300`) such reviews → `excellent_reviews.json` (repo, PR id/title/body/diff, reviewer id, review id, review body, inline comments, urls). Wide track = as many reviewers as reachable (toward `wide.target_reviewers`), mined free from the discovery index, for the scaling sweep.

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

**Contract and constraints** *(operator-only)*: OpenAI-compatible `llm_client.py`; key from `.env` (`QWEN_API_KEY`, never committed); Qwen may run concurrently (`qwen.max_concurrency`) — it is NOT the single GitHub worker. Qwen runs with **reasoning ON** (`enable_thinking: true`) for ALL calls — generation, reflection, the metric judge, and the quality judge — because Qwen is markedly weaker without thinking. **Never cap reasoning — no `max_tokens` throttle AND no `thinking_token_budget`.** Any reasoning cap makes the model GIVE UP and emit random noise, not a tighter answer — measured: kafka#17565 with `thinking_token_budget=2048` produced 26k chars of wandering and **0 tool calls** (it couldn't think the problem through, so it rambled instead of acting). `max_output_tokens` is the full window (`131072`), per-turn overrides removed, and `litellm_extra_body` carries `enable_thinking` ONLY — no budget key. The model stops naturally; the client strips `<think>…</think>`. Same RLVR lesson as the no-wall-clock-cap rule (P15): caps/limits are poison — let it think as DEEP as the problem needs. (A `thinking_token_budget` was once added here as a "rumination fix"; it was the opposite and is removed — do not reintroduce it.) Slower than no-think, accepted for quality; lean on `max_concurrency` for throughput.

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

Principle — don't artificially limit the review, and **never budget the model's reasoning**. Avoid caps or discouragement on the work the model does to produce a review: number of tool calls, breadth of delegations, investigation depth, priority cuts (reviewing only the top-N areas), character/context truncation of the diff or findings, "write the review now" early-stops, and **thinking/token budgets (`thinking_token_budget`, small `max_tokens`, per-turn output throttles)**. Rationale (RLVR/GEPA): the reward is the Claude judge's quality score and the prompt is optimized against it, so a hard limit tends to become something the model games rather than a budget it respects — under pressure to fit the cap it truncates or drops content and the review gets worse, not more concise. Worse, a cap on REASONING doesn't just shorten the output — the model can't think the problem through, **gives up, and returns random noise** (kafka#17565: a 2048-token thinking budget → 26k chars of wandering, 0 tool calls). We want it to go as DEEP as it needs. Quality is the only target; let the model investigate as much as the PR needs. The only bounds that belong here are the hard physical/safety ones — the vLLM context ceiling (P14), PTY avoidance (P13), and the runaway backstop `MAX_ORCH_STEPS` set well above real need — and even those are best met by scaling, compacting, or explicitly-marked truncation that never silently loses content (P14), rather than by telling the model to do less. The current `ORCH_SYS` anchors ("most reviews need 0-3 delegations", "over-delegating bloats synthesis", "write the final review now", changed-files-never-delegated) run against this and are the main v9 GEPA target — they're what cause the depth misses (see P15 and the `why-harness-under-investigates` finding).

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P11 (harness); the Contract above is binding.

**Reward:** a repo-reading review that beats diff-only consistently (not just low-base cases), with the policy GEPA-tunable.

**Attention mechanism:** agent+repo Δ over diff-only going negative on high-base reviews; a tool the P10 catalog needs but the loop lacks; any one subsystem problem (P12–P15) visibly dominant.

---

## P12 — Problem (runtime): the harness's execution substrate — reproducible, isolated, right-JDK-per-project.

**Value:** a substrate where the agent (now: its tools) can build, run, and test the repos — so future reality-check tools can verify a mechanical hypothesis against execution instead of imagining it, without poisoning the signal or contaminating the host.

**Contract and constraints** *(operator-only)*: **the whole harness runs INSIDE a Docker container** (operator decision, v8) — `docker/Dockerfile` (python 3.12 + openhands-sdk/-tools + git + ripgrep + JDK + maven), built as image `review-harness`, launched via `docker/run.sh` (the host Docker socket is mounted so the reality-check tool spawns SIBLING `review-java-<n>-sandbox` probe containers — see P17, which supersedes the run-`verify`-natively-in-this-same-container note below). The repo tree (`current_attempt/`, incl. `data/repos` and `results/`) is **mounted** (5.3G of checkouts — never baked); Qwen creds pass via `-e QWEN_API_KEY/QWEN_BASE_URL`; the Qwen endpoint is reached over the container network. **The harness Python is mounted, never baked** — `docker/Dockerfile` only `pip install`s deps (it does NOT `COPY src/`), and `run.sh` mounts `-v $PWD:/work`, so a code fix on the host is live for every harness container with NO image rebuild (and the per-JDK sandboxes are pure JDK+Maven — zero code/Python baked). Editing the host file is the whole deploy. The reality-check `verify` tool (P13) then runs `mvnw`/`gradlew` **natively in this same container** — no docker-in-docker. **Untrusted PR code only ever executes inside this container, never on the host.** Dependency caches are **named volumes** (`oh-m2-cache`/`oh-gradle-cache`), warm across PRs; a per-project JDK so a wrong JDK never yields a FALSE compile error that would poison the judge signal. The single-network-worker rule (P5) still applies to in-container fetches.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P12 (runtime); the Contract above is binding.

**Reward:** any sampled repo builds/tests in a clean container with the correct JDK and a warm cache, host uncontaminated.

**Attention mechanism:** a wrong-JDK false failure; a cold-cache blowup; PR test code about to execute on the host; the run becoming CPU-bound (→ request the offered server).

---

## P13 — Problem (tools): the tool layer the agent calls — correct, contract-faithful, single-call-useful, no-PTY.

**Value:** the tools through which the agent perceives the change and explores the repo; each must do exactly what its description says, in one call, without allocating a PTY.

**Contract and constraints** *(operator-only; DRAFT — review)*: subagents use `grep`/`glob`/`file_editor` (+`search`, +`pr_files`/`pr_file_diff`), **NEVER `terminal`** — both tmux and subprocess backends allocate PTYs → `out of pty devices`/`fork failed` at scale → subagent fails → review `0.0`. Every registered tool's prompt reference MUST match its registered name. `register_tool` idempotent (`register_*_if_absent` + a process guard) or the 2nd rollout errors and all score 0. Read-only against the host/repo: register no tool that writes the host checkout. The two deliberate non-read tools are write-elsewhere, not host-writes: `add_suspicion` (writes the in-process suspicion store, P15) and **`sandbox_exec`** (`src/current_version/sandbox.py`) — the fact-check-by-execution tool (P17) that runs arbitrary bash in a per-session remote Docker container (`review-java-<n>-sandbox` on server2 over `mh`) that mounts BOTH code versions (`version=new|old` → cwd `/src/new` post-PR / `/src/old` base — see P17): write a snippet/test, `javac`/`java`/`mvn`, read the result. It executes only INSIDE the container (never the host, never the repo tree), allocates **no PTY** (`docker exec` without `-t`), bounds each probe with an inner `timeout -k`, and logs every probe to `results/probes/<repo>__<pr>.log`. Given to the fact-checker so binding/signature/contract/runtime claims are proven by execution, not imagined; pairs with the default-REFUTE-when-unverifiable doctrine that kills the surviving fabrications (P15/P17). The 4-agent pipeline (P15) adds three more write-elsewhere tools — verdicts and fixes are CAPTURED BY A TOOL, never parsed from prose (a prose verdict silently defaulted to a lost finding): **`record_verdict`** (verdict + repro_kind test|log|grep + the reproduction = command(s) run & their output; a confirm OR refute reached without a run is coerced to `inconclusive`), **`record_fix`** (the solver's fix_diff + the verified rerun), and **`reset_workspace`** (the reproducer/solver resets both `/src` trees to pristine on demand; auto-reset also runs before each reproduction). The reproducer's edit surface is logging-only by job (it may add log lines, never logic); the solver gets full source edit but not the oracle (P15).

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

**Contract and constraints** *(operator-only)*: the orchestrator has **NO file tools** — the diff AND the changed-file context are injected into its first user message, so it reviews the changed files DIRECTLY and delegates ONLY for SURROUNDING/non-MR code (callers, conventions, impls elsewhere). Delegation is depth-2, **sequential** (orchestrator → `investigator` [+`task_tool_set`] → `code-explorer` leaf); the `task` tool is blocking, `tool_concurrency_limit=1`, `MAX_ORCH_STEPS=24` (a runaway backstop only — set well above real need, not a quality budget). Per the P11 don't-artificially-limit-the-review principle: the measured shyness (~3.8 delegations/PR, depth-2 fires ~1/29, voluntary stop at ~5–9 steps, well under the 24 cap) comes from `ORCH_SYS` anchors that run against it — "most reviews need 0-3", "over-delegating bloats synthesis", "write the final review now", and changed-files-reviewed-directly-never-delegated. These are the v9 GEPA target: delegations should scale to PR size, changed-file correctness (especially multi-instance checks — "verify all N overloads/call-sites") should be delegable, and depth-2 recursion should be a real trigger rather than a soft "may". Subagents MUST get the diff (repo is at BASE; added code is not on disk). The deliverable is the LAST `<review>…</review>` block (combine the finish action's `thought` then `message`, take `ms[-1]`). The finish tool nests its review under `action.message`, not a top-level `message` field — `model_dump().get("message")` returns `None`, so read `model_dump()["action"]["message"]`. Getting this wrong silently falls back to the model's `thought`, which `_post_think` strips to `""` (it ends in `</think>`), leaving an empty stored review. So an empty stored review is an extraction artifact, not a real 0 and not a synthesis stall — the full review sits in the saved orchestrator trace's `action.message` and is recovered deterministically (no rerun, no GitHub) by `src/recover_empties.py` (verified: hibernate-orm#11844, 4345 chars). Re-extract from traces before trusting any empty count.

Adopted architecture (2026-06-17, supersedes the four-agent and fact-check **suspicion-worklist** blocks below and the v8 delegation tree above; all kept as baselines): a **multi-investigator reproduce-and-fix** pipeline (`src/current_version/suspicion.py`), each agent given only the tools and the one reward its job needs. Stored via a tool, never a JSON blob (P14): suspicions through `add_suspicion`, verdicts through `record_verdict`, fixes through `record_fix`.
- **Orchestrator** — deterministic `run_suspicion_review`, `mode` ∈ {`mr`,`repo`,`both`} (env `INVESTIGATE_MODE`, default `mr`): runs one or both investigators, then the confidence-ranked reproduce/solve loop, then the concluder. Both investigators feed ONE worklist.
- **investigate_mr** — diff-anchored: read the PR, flag suspicions on the change. The **benchmark path** (P16: the human PR review is the oracle, which is diff-scoped — so the 200-PR quality benchmark runs `mode=mr`).
- **investigate_repo** — whole-repo bug sweep, the **RLVR path** (off for the benchmark — a bug three modules from the diff has no human-review oracle, but execution-confirmation IS the RLVR oracle, so whole-repo is a *cleaner* fit there). A `repo_map` tool injects orientation (Java modules + which have tests); the sweep is **biased to TESTED/exercisable modules** because only there can a suspicion be CONFIRMED by a run — and density of *confirmable* suspicions is what densifies the execution reward; a flood of grep-only suspicions is noise, not signal (it's exactly where precision collapses — the `volatile` non-bug). Suspicion-generation is cheap (prefill-heavy); the expensive reproduce/solve stays budget-bounded, so more candidates only raise the quality floor of the scheduled top-K — making confidence *calibration* as important as the wide net.
- **dedup-on-register** — `add_suspicion` runs a cheap **dedup SUBAGENT** (`DEDUP_SYS`) on every call: same underlying bug as one already listed? mr+repo+reproducer overlap heavily (same bug, different words) and dups would waste the reproduce budget. A dup **merges** into the existing suspicion (keeping the HIGHER confidence to raise its scheduling priority), not re-added; fail-open so a flaky dedup call never drops a real one.
- Each investigator records suspicions = {observation (the concrete thing literally seen), suspected_bug, location, confidence}; wide net, fire on sight, no self-vetting (downstream). **Confidence is the only priority signal** — severity/`value()` were dropped (severity was noise that stamped speculative concerns "critical" and buried a real low-severity bug at rank 14).
- **Scheduler** — deterministic `max(confidence)` (no LLM call): reproduce what the model is surest of first.
- **Reproducer** — get the REAL code to SHOW the bug, in the per-PR JDK sandbox (P17). Tools are narrow by design (see no_cheat-is-structural below): `edit_file` to add logging to an EXISTING file + `run_java` to build/test/run the real classes — no shell, no file-creation, so it CANNOT write a driver/copy. A verdict — confirmed *or* refuted — must be shown BY A RUN: confirmed = a test that fails / won't compile, or a log of a value wrong on `/src/new` but right on `/src/old` (the *flip*); refuted = a passing test / right value / a `grep` proving the suspected code is absent. Reading-and-concluding settles nothing → `inconclusive` (re-decide), never a free "refuted by reading" — that easy way out silently buried critical bugs (analysis-refuted criticals on the live trace). It also raises its own suspicions (closest view of the real code).
- **Solver** (separate agent, only on a confirmed bug) — same narrow tools (`edit_file`+`run_java`, no shell / no file-creation): edits the real code to fix it and re-runs the real check, leaving the reproducer's logging/tests (the oracle) untouched; graded by re-applying the reproducer's check to its patch: value now correct on `/src/new`, nothing else broken, smaller fix better.
- **Synthesize** — review = confirmed bugs (with their reproduction and, when present, the verified fix); `inconclusive` ones become hedged open questions.

**no_cheat is enforced STRUCTURALLY by the tool set** (2026-06-17, supersedes scorer-reconstruction as the *primary* guard — the scorer stays the eventual reward-binding mechanism): the reproducer AND solver have NO arbitrary shell and NO file-creating editor — only `run_java` (mvn/./mvnw/gradle/./gradlew/java/javac; rejects shell redirection / any write token) + `edit_file` (str-replace on an EXISTING file; refuses a missing path → cannot create) + read-only tools (no `file_editor`, which can `create`). So a copy/stub/standalone driver has **no tool that can bring it into existence** — the dominant failure the trace exposed (6/7 "confirms" were *simulations*: the model compiled a copy of the suspect logic and "reproduced" by construction; only a run that drives the real code, and flips when the real lines change, counts) is closed by construction. Operator rejected the post-hoc exec-guard (detect-new-file → withhold-output) as whack-a-mole; the fix is tool design, not bash-guarding. Validated quarkus#6913: /tmp-copy commands 14→0, 21 `edit_file` + 45 `run_java` + 31 real-file `javac`, 5 confirmed/5 fixed. Each agent still can't touch the thing that measures it (reproducer can't change logic; solver can't touch the oracle).

REWARD (locked 2026-06-16; the prompt is scaffolding, the reward is what the policy becomes — every behavior asked of an agent must map to a term or it won't stick, and the formula is shown verbatim in each agent's prompt). All terms are read by the scorer re-running genuine code, never the model's word:
- `R_suspector = Σ confidence over its CONFIRMED suspicions` — positive-only: a refute scores 0 (no timidity, wide net stays free), an off-diff suspicion can't be confirmed so it self-zeros (no penalty term needed). Confidence-weighted recall.
- `R_reproduce = no_cheat·(0.15·ran + 0.85·shown) + Σ confirmed(suspicions it raises)` — no_cheat = 1 by construction (the tool set allows nothing else), 0 only if a verdict is settled without a run; ran = real classes compiled+ran (a small carrot for the hard path); shown = a run settled it (flip / passing-run / grep).
- `R_solve = no_cheat·(0.10·ran_fix + 0.90·fixed·(1/LOC))` — no_cheat = oracle untouched & real-code-only (structural); fixed = re-run shows the value corrected & nothing else broken; `1/LOC` makes a tight root-cause fix beat a sprawling one.
Caveat for the training stage: confident-wrong is free in `R_suspector`, so a trained policy could inflate confidence — add a downside only then (it reintroduces timidity; a real trade). The **scorer that computes these by re-running genuine code is the next build** — today the formulas are shown to the model and outcomes are self-reported via the record tools (advisory, not yet binding); the structural tool set already makes `no_cheat` true by construction, which is the part the scorer would otherwise have to police.

**Three rollout rules, hard-won (2026-06-17):**
- **Never budget the model's reasoning** (no `thinking_token_budget`, no small `max_tokens`, no per-turn output throttle). A reasoning cap doesn't tighten the answer — the model can't think the problem through, gives up, and emits random noise (kafka#17565: `thinking_token_budget=2048` → 26k chars of wandering, 0 tool calls). Removed everywhere; let it think as deep as it needs (full window only). See P8.
- **Never cap a rollout by wall-clock.** Truncating mid-reasoning is a garbage RLVR rollout — the value is the COMPLETE trajectory + its reward, and a partial one has no clean reward and corrupts the signal. A slow run ≠ a failed one (a co-tenant load spike to ~100–140 made quarkus 3× slow; a 3h cap truncated it = wasted, no result). Bound runs only by (a) internal per-step caps (the sandbox's inner `timeout -k`, agent step caps — they end a run *gracefully* with a usable trajectory) and (b) a STALL detector (≥30 min with no new write to the reasoning log while a container is up) that pings a human to kill a genuine deadlock SURGICALLY. See memory `no-wallclock-cap-on-rollouts`.
- **A single transient LLM error must not crash the whole run.** A vLLM 400 (malformed/truncated tool-call JSON) in ONE `solve()` killed an entire review (17 suspicions' work lost) — the same waste as a truncation. `_run_agent` now catches any `conv.run()` exception, logs it, and returns whatever partial output the agent produced; the caller records `inconclusive`/no-fix and the pipeline continues to the next suspicion.

Prompts are plain-voice problem-and-reward, no caps/imperatives/checklists (those read as a leash and make the model worse) — pose the problem, show the reward formula, let it find the method.

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P15 (topology); the Contract above is binding.

**Reward:** the smallest investigation that fully answers and self-terminates and emits a clean extractable review — beating diff-only without cratering.

**Attention mechanism:** never self-terminating (8/8 steps); delegation count climbing (over-delegation → slower + more stalls); the same file read many× across subagents; an empty/garbled review (a same-PR review is never truly empty — first suspect the `action.message` extraction bug above and recover from the trace; only if the trace's finish message is itself empty is it a genuine synthesis stall = `0.0`); depth-2 not firing. New (multi-investigator) signals: a `cat >`/copy in the probe log (a cheat — but FIRST check it isn't a stale un-truncated prefix); a confirm via `grep` where a `test` was possible (weak evidence — the precision gap); `investigate_repo` flooding grep-only suspicions on untested code (noise, not confirmable reward); dedup merging two DISTINCT bugs or dropping a real one (over-dedup); a run dying `exit≠0` (crash — a transient LLM 400 should now be caught, not fatal) or `exit=124` (a wall-clock cap crept back in — forbidden).

---

## P16 — Problem (measurement): a trustworthy per-review score with its evidence on disk.

**Value:** know whether reading the repo helps and at what cost — the evaluation capability P2's optimization and P11's comparison both rely on. Clusters with the eval concern (P2), numbered here because it scores the harness.

**Contract and constraints** *(operator-only)*: **the judge is CLAUDE, never the reviewer model** — a model grading its own reviews shares its blind spots (Qwen self-judging certified its own fabrications: `sevntu#645` Qwen +9 vs Claude −13). Comparison is **3-WAY**: `mr` (diff only) / `mr_code` (diff + full changed files, no tools) / `mr_code_tools` (+ tools + delegation) — so `mr→mr_code` measures "do the full files help?" and `mr_code→mr_code_tools` measures "does exploring the rest of the repo help?". Metric = code-grounded **POINT judge**: per finding good `+1` / critical `+2` / wrong `−1` (verify against the code first) / trivial `0` (praise/restating = 0), minus `−1` per missed human∪Claude point; the judge MUST have repo access (a text-only judge always returns `wrong=0` and misses fabrications). The judge should grade on complete data — the full PR diff (the same `full_pr_input`/`full_pr_diff` the reviewer saw, not the dataset's ~7k-char truncated `input`) plus repo access at the base commit. Grading on partial/truncated context isn't valid: points that cite code outside the window become "unverifiable" (scored 0), which quietly deflates net and also masks fabrications (you can't refute a claim about code you can't see). If the repo is busy (e.g. a generation container holds the working tree), assemble the full diff read-only with `git diff <base_sha>...pr-<pr>-head` on the already-fetched local branch — not `checkout` (corrupts the container's tree) and not re-`fetch` (violates the single-GitHub-worker rule P5). Blind own-review FIRST. When the measurement protocol changes, RE-MEASURE the whole `n` fresh, don't backfill. Qwen-judged numbers are cost-telemetry only. Two judges, two jobs (2026-06-16): the Claude point-judge stays the **quality oracle** for whether a review is good, but it is too expensive/slow to be a per-rollout RL signal. The per-rollout reward is the **verifiable execution reward** of P15 (`R_reproduce`/`R_solve`/`R_suspector`, computed by a scorer re-running genuine code) — cheap, machine-checkable, aligned by construction (it *is* "did the real lines drive the outcome"). Claude's role for that reward is the periodic **auditor**: validate the cheap reward against the point-judge on a sample before trusting it for a ralph loop or GRPO — and that audit already caught the simulation hole (6/7 execution-"confirms" were synthetic copies, so the raw execution-pass signal was *misaligned* until the scorer's pristine-reconstruction was added; train on the unaudited signal and you teach better simulations, not bug-finding). The scorer itself is the next build; until it lands the P15 formulas are advisory (model-self-reported via the record tools), and the point-judge is still how we grade a run. The **200-PR quality benchmark runs `mode=mr`** (diff-anchored, P15): the human PR review is the oracle and is diff-scoped, so whole-repo (`investigate_repo`) findings would score as false positives against it — whole-repo is RLVR-only, where execution-confirmation, not the human review, is the oracle. Run sequentially or in a small fixed number of lanes via a flock work-queue (be a polite GPU co-tenant, P18); a benchmark is run-once so throughput isn't the constraint (no build-cache needed — per-review wall-clock is dominated by the agent loop, not the build).

**Solution search approach and hints:** the implementation knowledge lives in the `harness` skill (`.claude/skills/harness/SKILL.md`), §P16 (measurement); the Contract above is binding.

**Reward:** a per-PR net score you can trust, with its trace on disk.

**Attention mechanism:** the measurement protocol changes (token capture, judge, rubric); a `judge=None` hole; the metric misranks a verified-find review; a Qwen-judged number about to be used as a quality claim.

---

## P17 — Problem (verification sandbox): a remote Docker host where the fact-checker proves a suspicion by EXECUTION, not by reading.

**Value:** text tools cannot settle the claims that produce our worst errors — wrong-overload/signature, comparator-contract, NPE, "this won't compile", and especially external-library/API behavior (measured: the fact-checker *confirmed* a false Spanner-REST claim on hibernate#11945 it had no way to refute, and over-hedged real findings into open questions because it could not positively verify them). The compiler is the exact oracle for binding/signature/type; the runtime is the oracle for behavior. Giving the fact-checker (P15) a place to compile/run/trace against the REAL project classpath turns "imagined" verdicts into executed ones — fabrications that survive text-checking die on execution, and hedges become decisive.

**Contract and constraints** *(operator-only; DRAFT — review)*: the host is **server2** (`mh` = `mikhailov.tech:2222`, user `vmihaylov`, Docker 27.5.1, in the `docker` group — this LIFTS the prior read-only-`mh` rule), a native-Linux box (24 cores / 125G) that is ALSO the inference host (Qwen vLLM behind Caddy). **Compose with the `bump_java_version` substrate cluster already on this box — do NOT reinvent it:** resolve all deps through its **Nexus** caching proxy by container-network DNS (its P5); obey its docker-bounded discipline (its P6) — the host is only a Docker host, **untrusted PR/build code executes only inside a container, never on the host**; write probe logs under `/var/log/observe/app/` so its frog's-eye digest (its P10) sees them; respect its saturation governor (its P9) — builds are CPU/RAM/IO (they don't fight the GPU) but cap parallelism and **watch disk (was 84% used / 143G free)**. Two hard-won substrate rules are binding here: **bound every probe with an INNER `timeout -k`** (a host-side / `docker exec` client timeout does NOT kill the container — a hung build survives holding cache locks), and **cap container json-file logs** (`log-opts max-size/max-file`) or one run silently fills the disk. WE own only: **per-JDK images named `review-java-<n>-sandbox`** — all five LTS now built (`n` ∈ 8/11/17/21/25), each a single JDK + Maven with `settings.xml` pointed at Nexus (Gradle later). **Pick the image by the repo's BUILD floor, detected EMPIRICALLY — not by its declared level.** A wrong JDK yields FALSE compile errors that poison the verdict (P16): quarkus#6913 (Java-8-target 2020 code) on the default JDK 21 threw 719 false errors (`package sun.misc does not exist`, enforcer `enforce-java-version` rejected) and the reproducer thrashed; routed to JDK 11 it compiles, and the pipeline produced a `confirmed/test` + a verified fix. The declared `maven.compiler.*` is the *bytecode target, not the build floor* (quarkus declares `source 1.8` but needs JDK 11 to build), so **confirm by compiling, not by parsing**. Two skills carry this — REUSE, don't reinvent: **`detect-java-version`** (`skills/detect-java-version/SKILL.md` — probe-compile across the LTS images, pick the lowest that builds, start it) and **`bump-java-version-skill`** (`github.com/vasiliy-mikhailov/bump-java-version-skill` — the symptom→fix table for toolchain false-errors: Lombok floor, re-add EE/JAXB deps, surefire/Mockito/ByteBuddy/JaCoCo bumps, `--add-opens`; class-file→JDK map v52=8…v69=25). `detect_jdk` in `sandbox.py` currently pom-parses (fragile by that lesson) and is to become the empirical probe — ideally an OpenHands detector step that reads `detect-java-version`, probes, and starts the proper container before the suspector runs. The session container auto-resets both trees to pristine before each reproduction (`sandbox.reset_clean` = git checkout+clean, run harness-side since the worktree's gitdir only resolves there) and exposes a `reset_workspace` tool, so the reproducer's logging and the solver's patches never leak across checks. **One NAMED, persistent container per review session** (`review-<repo>-<pr>`) mounting **BOTH versions** + warm `~/.m2`, created at session start, each probe run via `docker exec`, every probe logged (cmd/stdout/stderr/exit) for `docker exec`-in inspection and as the grading/audit trail, torn down at session end (scratch reaped via a root container, not host `rm`). **Mount both, default to post-PR (the under-confirm fix, 2026-06-15):** base → `/src/old`, a `pr-<pr>-head` git **worktree** (`data/repos/<slug>__new-<pr>`, fall back to HEAD) → `/src/new`, cwd `/src/new`. The fact-checker/generator **read surface is version-aware**: the agent workspace points at the post-PR worktree so `search`/`grep`/`glob`/`file_editor` read the PR's resulting code BY DEFAULT — added/renamed files ARE on disk (base-only was the dominant under-confirm cause — 6913 conf=1/part=10 — because the whole read+exec surface could not see the post-PR code); the reproduce/solve agents drive execution via **`run_java`** (`version=new|old` → cwd `/src/new` vs `/src/old`; mvn/./mvnw/gradle/./gradlew/java/javac only, no shell) + **`edit_file`** (existing-file str-replace, no create), which REPLACE the old arbitrary-bash `sandbox_exec` for those agents (the structural no_cheat of P15 — `sandbox_exec` is retired from their tool sets); `pr_file_diff` stays version-independent (− base, + post-PR). The probe log is **truncated per run** (`open(probe,'w')` as root in `run()`, mirroring the reasoning log) — a re-runner's `rm` can't delete the root-owned probe file, so without truncation it ACCUMULATES across runs and a stale pre-structural-tools prefix (with `cat > X.java` copies) poisons the copy-cheat audit. Reap the worktree in `stop()` alongside the container. NOTE: inside the sandbox `git -C /src/new` fails (the worktree's `.git` metadata is not mounted) — by design; only files + `javac` are needed there. Two probe tiers: **Tier A** self-contained snippet (no project classpath — comparator/locale/off-by-one), **Tier B** compile/run/trace against the real project classpath via Nexus. Pairs with a doctrine the fact-checker must hold: **default-REFUTE when no probe can positively verify** (the rule that kills the Spanner-type fabrication). This is the reality-check tool foreseen in P12/P13 and the missing falsification muscle for P15's fact-check role.

**Solution search approach and hints:** start Tier A on this host (no project build needed) to prove the execute-to-verify idea on the two PRs that exposed the leak (11945 fabrication, 6222 under-coverage); only then invest in Tier B per-repo warm images for the heavy builds (trino/hibernate). When a build fails on dependency resolution, widen Nexus upstreams before treating it as code-attributable (its P5). Re-enter whenever a fact-check verdict rests on an unexecuted mechanical/structural/runtime claim, or a build false-fails on the wrong JDK.

**Reward:** a suspicion's mechanical/structural/runtime claim is confirmed or refuted by actual `javac`/`java`/`mvn` output rather than imagined; fabrications that pass text-checking fail execution; host + inference endpoint stay uncontaminated and within their resource bands.

**Attention mechanism:** a fact-check confirming a claim with no executed evidence; a wrong-JDK false compile error; a probe/container outliving its run (failed inner-timeout/reap) holding cache locks; container logs or disk creeping toward full; the inference endpoint degrading while a build runs.

---

## P18 — Problem (maintain remote environment): one pinned home on the build host, scratch/disk/cache stewardship, so iteration variance comes only from what's measured.

**Value:** the harness, the repo checkouts, the dep caches, and the verification sandbox (P17) all share **server2** — which is also the live inference host. Unstable paths, leaked scratch, a runaway container, or a full disk drift the reward's noise floor up and can crash a co-tenant (worst case: the Qwen service we depend on). One pinned, stable home and disciplined cleanup keep the box reproducible and a good neighbour. This is the REMOTE execution home (distinct from the laptop's `current_attempt/` dev workspace at the top of this file): code/repos/venv that actually run live here so the agent, the repo it reads, and the build it runs are co-located (resolves the "where does OpenHands run" split — the in-process LocalWorkspace and the sandbox must be on the SAME box or Tier-B compile-against-the-real-classpath is impossible).

**Contract and constraints** *(operator-only; DRAFT — review)*: the project home on server2 is **`~/great-java-review`** — the one path pinned here; every other location is an env var resolved from `.env` next to the credentials (repo mirrors, scratch roots, results). Compose with the `bump_java_version` substrate cluster already on this box (do not reinvent): deps resolve through its **Nexus** by container-network DNS; **every action is docker-bounded** — the host is only a Docker host and a bind-mount source, never a place to run build/PR code directly; **SSH calls share one session**, not one per command; **free host resources the inference service needs** (builds are CPU/RAM/IO, the GPU is the service's — never contend for it). Two disk/lifecycle rules are binding (their hard-won lessons): **bound every build/probe with an inner `timeout -k`** (a host-side / ssh-client timeout kills the `docker` client, NOT the container — a hung build survives for days holding cache locks), and **cap container json-file logs** (`log-opts max-size/max-file`; one unbounded log hit 55 GB and filled a disk — and ours sits at ~84% used). Each run **reaps its own scratch in a `finally` via a ROOT container** (the build container writes root-owned files; host `rm` can't) — a scratch dir or `review-*` container that outlives its run is a reap failure to investigate, not just to clean. Repos cached under the home (e.g. `~/great-java-review/data/repos/<owner>__<repo>`), `~/.m2` warm via Nexus + a named volume.

**Solution search approach and hints:** pin the home and the caches; when a pattern is slow or rate-limited, cache it once; never let docker-owned root-rw files leak — clean through a root container, never host `rm`. When disk or the per-repo container/scratch count creeps, fix the reap (the leak), don't just sweep. Re-enter whenever a `review-*` container or scratch survives its run, disk/log size climbs, or the inference endpoint degrades while we build.

**Reward:** iteration variance from non-measured factors approaches zero — zero disk-full crashes, zero stray containers/scratch dirs, predictable per-iteration wall-clock, the inference endpoint unharmed by our load.

**Attention mechanism:** host state is the channel — a `review-*` container or scratch dir outliving its run, container-log or disk size creeping toward full, or the inference endpoint degrading during a build, signals P18 to fix the reap/limit before the next iteration counts. The shared host also PRUNES images under disk pressure (`review-harness` and `review-java-<n>-sandbox` both vanished mid-session, freeing ~25G) — so build-on-demand: verify/rebuild both images at the start of a run, and treat a `Unable to find image` / `pull access denied` at launch as the signal to rebuild, not a code error.

---

## P19 — Problem (bug fixing): reproduce, root-cause, fix the cause, rerun clean — never a workaround.

**Value:** a bug fixed at its root removes a whole failure class and leaves the code smaller; a bug papered over with a guard/special-case hides the cause, corrupts data downstream, and accretes into the kind of cruft this project keeps stripping. The discipline is what keeps the harness honest enough to trust its own measurements.

**Contract and constraints** *(operator-only)*: when something breaks, (1) REPRODUCE it (a real trace, not a guess); (2) find the ROOT cause — the actual mechanism (e.g. "the fact-check passes the whole ~150k-char PR context to a multi-turn agent, so it overflows `max-model-len` → 400"), not the symptom ("a check errored"); (3) fix the ROOT — change the thing that is wrong so the error cannot occur, do NOT add a `try/except`, a "treat as X on failure", a retry, a cap, or any mask that lets the broken path keep running; (4) RERUN CLEAN to confirm the fix and that the error is gone; (5) clean up any CONSEQUENCES the bug or a prior wrong-fix left behind (corrupted outputs, litter, dead guards). A workaround is acceptable only as an explicitly-labelled, temporary stopgap with the root-cause fix tracked — never as the resolution. This contract is now operationalized as the review pipeline's **Solver** (P15): reproduce (the reproducer's run shows the bug) → fix the real lines → rerun the same check clean → `R_solve` rewards `fixed·(1/LOC)`, so the smaller, root-cause fix scores higher and a sprawling workaround scores worse. We hold our own harness to it too: the session's bugs (the 400-overflow, the silent partial-default, the wrong-JDK false errors) were each root-caused and fixed, not masked. **One principled exception: boundary fault-isolation.** Catching a TRANSIENT EXTERNAL fault — a per-rollout vLLM 400 on the model's own malformed tool-call JSON — at the agent boundary so it doesn't destroy unrelated work (every other suspicion in the run) is fault-tolerance, not masking; it's distinct from swallowing a deterministic bug in our own logic, which stays forbidden. The test: does the `try/except` hide a root cause we could fix (mask → forbidden), or isolate an inherent external flake so good work survives (tolerate → allowed)? The P15 `_run_agent` catch is the latter.

**Solution search approach and hints:** trace on the host (logs, the real request/response, the actual mount) before theorising — you can almost always reproduce deterministically. When a fix ADDS code (a guard, a branch, a retry), suspect you are masking; the root-cause fix usually REMOVES code (the redundant context, the wrong path, the duplicated state). Re-enter whenever an error is being caught-and-continued rather than prevented.

**Reward:** less code and fewer workarounds after the fix than before — a resolved bug that deletes a special-case beats one that adds a guard. Zero masks left in the resolved path; the rerun is clean.

**Attention mechanism:** the diff is the channel — a `try/except` that swallows, a "default to X on failure", a retry around a deterministic error, or a cap that hides an overflow, each signals the symptom was treated, not the cause; re-open until the root is fixed and the mask is gone.
