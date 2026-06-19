# AGENTS.md

A delegation protocol, not a checklist. Each entry is a **problem**: one
autonomous concern the operator has offloaded to the agent. Clustered — meta
(P1); recipe/setup (P2–P4); substrate (P5–P10, P17–P18); harness (P11–P15);
evaluation (P16); discipline (P19).

> **WORKSPACE CONVENTION (operator-set).** ALL work happens in **`current_attempt/`**
> — the single live directory (`src/`, `data/`, `results/`, `excellent_reviews.json`;
> `venv` and `.env` are symlinked from the repo root, so code runs with
> `cwd = current_attempt`). Snapshots are made ON REQUEST as read-only copies →
> `attempt_N/`. **Never edit or run inside an `attempt_N/` snapshot.** Deploy to
> server2 is `rsync`/`scp` of `src/current_version/` (its git is stale by design).

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

**Value:** prompts that make the model produce a reviewer's **high-quality reviews** in their voice — per-reviewer and one universal. We mimic their substantive technical feedback (real pain points), NOT LGTM/nits/process chatter. Delete this and nothing else has a reason to run.

**Contract and constraints** *(operator-only)*: GEPA reflective evolution; task + reflection model = the active profile (`qwen`, model-agnostic via profiles). Produce per-reviewer AND one universal prompt, then a held-out comparison vs the `SEED_SINGLE` baseline. Mimicry metric = `0.85·LLM-judge + 0.15·lexical` vs the real review. **The ceiling is the two-human same-PR agreement ≈ `0.485`** (`results/score_calibration.json`), not 1.0; floor ≈ `0.04`, excellent ≈ `0.48+`. Qwen ≈ `0.29` (~56% floor→ceiling) — closing that gap is the goal (P10 / Attempt 2 chase it).

**Solution search approach and hints:** custom `GEPAAdapter` in `gepa_run.py`; cost bounded by `max_metric_calls`, not trainset size; inspect a run via `gepa_chart.py <run_dir>`.

**Reward:** best-candidate held-out score, measured against the `0.485` ceiling.

**Attention mechanism:** a reviewer's dataset reaches usable size, or a seed/metric/budget edit.

---

## P3 — Problem (reviewer corpus): a reproducible dataset of high-signal Java reviewers and their reviews.

**Value:** the per-reviewer training/eval data P2 learns from — real PRs with their substantive human review comments, deduped and quality-filtered.

**Contract and constraints** *(operator-only)*: `excellent_reviews.json` (23-repo corpus, ~1752 qualifying human-reviewed PRs). A review unit = (PR diff, reviewer, their substantive comments). Filter out LGTM/nits/process. `crawl._review_units` indexes them; `sample_prs.py` selects N. Honor the single-GitHub-worker rule (P5) when fetching.

**Solution search approach and hints:** grow coverage per reviewer until a reviewer has enough PRs to train/hold-out; prefer reviewers with dense technical comments.

**Reward:** enough high-signal PRs per reviewer to train and hold out.

**Attention mechanism:** a reviewer crosses usable size; a corpus-quality complaint.

---

## P4 — Problem (scaling curve): does ONE universal prompt suffice as the reviewer set grows?

**Value:** know whether per-reviewer prompts are needed or one universal prompt generalizes — decides where P2 invests.

**Contract and constraints** *(operator-only)*: measure universal-vs-per-reviewer held-out score as the reviewer count grows; the question is empirical, re-asked as the corpus (P3) expands.

**Solution search approach and hints:** plot universal and per-reviewer curves vs reviewer count on the same eval.

**Reward:** a clear answer at the current corpus size, re-checked as it grows.

**Attention mechanism:** the reviewer set grows materially.

---

## P5 — Problem (GitHub politeness): never get the token banned.

**Value:** a durable GitHub presence — fetches never trip abuse detection or burn the token.

**Contract and constraints** *(operator-only)*: **exactly ONE GitHub worker at a time** (crawl XOR a container fetch — never both). The `gh` token comes from the OS keyring, **never written to disk**, never committed. Rate-limit-aware, backoff on 403/secondary limits. Do NOT open PRs to Apache (or any) upstream without explicit operator go — their identity, their reputation.

**Solution search approach and hints:** serialize all network access through one worker; cache aggressively so a pattern is fetched once.

**Reward:** zero bans, zero secondary-limit storms, token never on disk.

**Attention mechanism:** a 403/secondary-rate-limit; two network workers about to run; a token about to touch disk.

---

## P6 — Problem (job durability): long jobs survive interruption and resume.

**Value:** a multi-hour run that is interrupted resumes from where it stopped, not from zero.

**Contract and constraints** *(operator-only)*: append-only progress to disk (e.g. `results/*.jsonl`); a flock work-queue for parallel lanes that pop atomically; resumable by re-reading state. Long local jobs run under `caffeinate -dimsu` (a closed lid suspends the process and looks like a hang).

**Solution search approach and hints:** make each unit of work idempotent and recorded before/after; a resumed run skips completed units.

**Reward:** an interrupted job resumes with no lost or double work.

**Attention mechanism:** a crash/interruption; work being redone on resume.

---

## P7 — Problem (dependency isolation): no dependency hell.

**Value:** code runs the same on the laptop and the build host, with no version drift.

**Contract and constraints** *(operator-only)*: the working venv (`venv`) stays untouched; the OpenHands harness uses a separate `venv-oh` (Python ≥3.12). Pin SDK versions (OpenHands V1 fields churn). The harness itself runs in a Docker image (`review-harness`) with deps baked but code **mounted** (P12).

**Solution search approach and hints:** separate venvs per concern; pin; never mix the harness env into the working env.

**Reward:** a fresh checkout runs both tracks without a dependency fight.

**Attention mechanism:** an import/version error; an env that only works on one machine.

---

## P8 — Problem (Qwen endpoint): the model under optimization is reachable and bounded-cost.

**Value:** GEPA/harness calls hit Qwen reliably within budget.

**Contract and constraints** *(operator-only)*: OpenAI-compatible `llm_client.py`/`llm.py`; key from `.env` (`QWEN_API_KEY`/`QWEN_BASE_URL`, never committed); Qwen may run concurrently (`qwen.max_concurrency`) — it is NOT the single GitHub worker. **Reasoning ON** (`enable_thinking: true`) for ALL calls — generation, reflection, judges — Qwen is markedly weaker without it. **Never cap reasoning — no `thinking_token_budget`, no small `max_tokens`, no per-turn output throttle.** A reasoning cap doesn't tighten the answer; the model can't think the problem through, **gives up, and emits noise** (kafka#17565 with `thinking_token_budget=2048` → 26k chars of wandering, 0 tool calls). Use the full window (`131072`); `litellm_extra_body` carries `enable_thinking` ONLY. Transport is **streaming** (`stream=True` via a `StreamingLLM(LLM)` subclass) so the read-timeout fires only on a genuinely silent socket, not on a long generation; `num_retries` rides out transient drops. Same RLVR lesson as the no-wall-clock-cap rule (P15): caps are poison.

**Solution search approach and hints:** bound spend via GEPA `max_metric_calls`; lean on `max_concurrency` for throughput. Transport-debug detail in the `harness` skill.

**Reward:** endpoint returns 200; per-run cost within budget.

**Attention mechanism:** a non-200; runaway call volume; a reasoning/output cap creeping back in.

---

## P9 — Problem (auto-tune): AutoResearch loop that climbs toward the config maximizing mimicry quality.

**Value:** find the config maximizing held-out mimicry (P2) via a trajectory-informed keep/revert loop, not blind search.

**Contract and constraints** *(operator-only)*: Karpathy-style — propose a TARGETED change informed by past trials, run a comparability-budgeted trial (`gepa_seconds`), KEEP if it beats the incumbent else REVERT. The budget is not the mechanism; the informed hypothesis is. HOLD measurement FIXED (same eval PRs, same metric) so a win can only be genuinely closer reviews. Tune on one well-covered reviewer (`vietj`); validate the winner on others before adoption. Escalation: knobs first, then pivot to editing prompt seeds/code once knobs saturate.

**Solution search approach and hints:** engine `src/autoresearch.py` (resumable via `results/autoresearch.jsonl`); outer loop = the `autoresearch` skill (the agent supplies hypotheses beyond the knob grid).

**Reward:** best held-out mimicry score across trials.

**Attention mechanism:** a trial beats best-so-far; knobs saturate (→ pivot to code); the objective changes.

---

## P10 — Problem (context beyond the MR): what data do two AGREEING humans both use?

**Value:** identify the data — beyond the MR diff — two reviewers both draw on when they **agree**, so the agent can be given it and close the Qwen→ceiling gap (P2).

**Contract and constraints** *(operator-only)*: convergence is the signal — when two experts independently raise the SAME point, it is determined by **shared context the diff doesn't contain**: issue-tracker links, the broader codebase, project conventions, prior PR/design discussion, commit history, the contract of touched APIs. Catalog these, ranked by how strongly they drive agreement; that defines the tool/context set the agent must read.

**Solution search approach and hints:** mine high-agreement same-PR human pairs (samePR score ≥ ~0.6 in the `crawl._review_units` index); tag every reference to non-diff data; contrast with low-agreement pairs (what context was missing).

**Reward:** a ranked catalog of non-MR context sources that correlate with two-human agreement.

**Attention mechanism:** the Qwen-vs-ceiling gap; a new context source in an agreeing pair; agent tool design (P11).

---

## P11 — Problem (harness): the loop that lets Qwen read the repo to review.

**Value:** a controllable agent loop that feeds the model the non-MR context (codebase, conventions, API contracts) and whose POLICY P2's GEPA can optimize. The assembled machine; its subsystems are P12 (runtime) / P13 (tools) / P14 (compaction) / P15 (topology), and P16 evaluates it. A fix that changes for a subsystem reason lives there, not here.

**Contract and constraints** *(operator-only)*: harness = the **OpenHands V1 Agent SDK** (`openhands-sdk` + `openhands-tools`), NOT the heavy `openhands-ai` monorepo. Loop contract: per-rollout system-prompt override = the genome; score the FINAL artifact only (with thinking extraction); extract the tool trajectory for reflection; point at the thinking-Qwen endpoint (P8); think on; pin SDK versions. **Don't artificially limit the review** — no caps on tool calls, delegation breadth, investigation depth, priority cuts, diff/finding truncation, "write it now" early-stops, or reasoning (P8): a hard limit becomes something the model games (drops content) or gives up on (emits noise). The only bounds are the hard physical ones — the vLLM ceiling (P14), PTY avoidance (P13), a runaway backstop well above real need.

**Solution search approach and hints:** implementation knowledge in the `harness` skill, §P11; the Contract is binding.

**Reward:** a repo-reading review that beats diff-only consistently, with the policy GEPA-tunable.

**Attention mechanism:** agent+repo Δ over diff-only going negative on high-base reviews; a tool the P10 catalog needs but the loop lacks; any one subsystem (P12–P15) dominant.

---

## P12 — Problem (runtime): the harness's execution substrate — reproducible, isolated, right-JDK-per-project.

**Value:** a substrate where the agent's tools can build/run/test the repos, so a hypothesis is verified against execution, without poisoning the signal or contaminating the host.

**Contract and constraints** *(operator-only)*: **the whole harness runs INSIDE a Docker container** (`docker/Dockerfile` → image `review-harness`, launched via `docker/run.sh`; the host Docker socket is mounted so it spawns SIBLING `review-java-<n>-sandbox` probe containers — P17). The repo tree is **mounted** (`-v $PWD:/work`, never baked) and the harness Python is mounted too — **a host edit is the whole deploy, no rebuild**. Qwen creds via `-e`; `INVESTIGATE_MODE` forwarded. Dep caches are named volumes (`oh-m2-cache`/`oh-gradle-cache`), warm across PRs. **Untrusted PR code only ever executes inside a container, never the host.** A per-project JDK so a wrong JDK never yields a false compile error (P16/P17).

**Solution search approach and hints:** implementation in the `harness` skill, §P12; the Contract is binding.

**Reward:** any sampled repo builds/tests in a clean container with the right JDK and a warm cache, host uncontaminated.

**Attention mechanism:** a wrong-JDK false failure; a cold-cache blowup; PR code about to run on the host.

---

## P13 — Problem (tools): the tool layer the agent calls — correct, contract-faithful, single-call-useful, no-PTY.

**Value:** each tool does exactly what its description says, in one call, without allocating a PTY.

**Contract and constraints** *(operator-only)*: read tools = `search`/`grep`/`glob`/`file_editor`/`pr_files`/`pr_file_diff`; **NEVER `terminal`** (PTY → `out of pty devices`/`fork failed` at scale → review `0.0`). Every tool's prompt reference must match its registered name; `register_tool` idempotent or the 2nd rollout errors. Outcomes are **CAPTURED BY A TOOL, never parsed from prose** (a prose verdict silently became a lost finding). The write-elsewhere tools of the pipeline (P15), none of which write the host checkout: `add_suspicion` (in-process worklist, runs a dedup subagent); `record_verdict` (verdict + `repro_kind` regression_test|test|log|grep + the reproduction; captures `test_path`/`test_src` read from disk; a verdict reached without a run coerces to `inconclusive`); `record_fix` (the solver's diff + the passing-test rerun); `reset_workspace`; `repo_map`. The reproduce/solve **edit+run** tools live in P15's structural no_cheat set (`run_java`/`edit_file`/`create_test`); arbitrary-bash `sandbox_exec` is retired from those agents.

**Solution search approach and hints:** implementation in the `harness` skill, §P13; the Contract is binding.

**Reward:** every registered tool does what its description says in one call; zero hallucinated-tool errors.

**Attention mechanism:** a `Tool 'X' not found`; `out of pty devices`; a non-idempotent register; a tool returning truncated/misleading output.

---

## P14 — Problem (compaction): context stays BOUNDED and COHERENT across a multi-turn review.

**Value:** the agent never blows the window nor loses the thread to a garbled summary.

**Contract and constraints** *(operator-only)*: token-based compaction (`LLMSummarizingCondenser`). `keep_first` MUST cover the PR message (`keep_first=6`) or the agent synthesizes blind. **INVARIANT:** `condenser.max_tokens + agent.max_output_tokens ≤ max-model-len` — vLLM ERRORS if `prompt + requested_output > 262144`; with output `131072` set `condenser.max_tokens=120000`. The condenser LLM is cloned with `enable_thinking=False`. Tie the two: change one, move the other.

**Solution search approach and hints:** implementation in the `harness` skill, §P14; the Contract is binding.

**Reward:** history never crosses budget; each summary shrinks context and stays factual.

**Attention mechanism:** a summary opening `"Here's a thinking process:"` or larger than what it replaced; a vLLM `prompt + output > model-len` error.

---

## P15 — Problem (topology): the pipeline that finds, proves, and fixes bugs as registry entries.

**Value:** the cheapest agent pipeline that surfaces real bugs, proves each with a unit test, and fixes it — buying real depth without paying for over-exploration.

**Contract and constraints** *(operator-only)*: a deterministic **registry pipeline** (`src/current_version/suspicion.py`), each agent given only the tools and the one reward its job needs; everything stored through a tool, never a prose blob (P13). The registry is three linked entry types — **Suspicion → Bug → Solution** — with phase-separated hand-off:
- **Investigators → Suspicions.** `run_suspicion_review`, `mode` ∈ {`mr`,`repo`,`both`} (env `INVESTIGATE_MODE`, default `mr`). `investigate_mr` reads the diff (the **benchmark path** — the human review oracle is diff-scoped, P16); `investigate_repo` sweeps the whole repo biased to TESTED modules via `repo_map` (the **RLVR path** — execution is the oracle there). A Suspicion = {observation, suspected_bug, location, confidence}; wide net, fire on sight. `add_suspicion` runs a **dedup subagent** (merge into the higher-confidence existing entry; fail-open). **Confidence is the only priority signal** (severity was noise).
- **Reproducer → Bugs.** Scheduler picks `max(confidence)`. It must SHOW the bug with a **unit test** in the per-PR JDK sandbox (P17): a JUnit `@Test` that fails on the bug — `edit_file` it into an existing `*Test.java`, or `create_test` a new one. `repro_kind` `regression_test` > `test` > `log` > `grep`. Coupled code is reached by **mocking collaborators** (never the class under test: Mockito `mock().thenThrow`/`mockStatic`/`catchSystemExit`/`SecurityManager`); it MAY add `org.mockito:mockito-core` at TEST scope if absent. A verdict is shown BY A RUN or it is `inconclusive`. `test_src`/`build_edit` captured **from disk** (authoritative over the paste). A proven suspicion becomes a Bug.
- **Solver → Solutions.** Separate agent, **only on a Bug that carries a unit test** (grep/log-only bugs are left for the author, not guessed). It re-materializes the test (+ build_edit) into a clean tree and fixes production with `edit_file` + `run_java` until green; gentle framing "fix the code so the test passes." **`R_solve = passes · 0.9^(lines_changed) · test_untouched`** — `passes` = test now passes (no-test bug self-zeros); `lines_changed` MEASURED by git (production only); `test_untouched` = 0 if it changed even one test line (it CAN, the reward says don't — no structural lock).
- **Synthesize → PR.** Reads the registry: each Bug with its test and, when present, its verified fix; `inconclusive` suspicions become hedged open questions.

**no_cheat is structural** (the tool set, not a post-hoc guard): reproducer/solver get only `run_java` (mvn/gradle/java/javac; rejects redirection/write tokens), `edit_file` (str-replace on an EXISTING file), and `create_test` (a NEW file ONLY under `src/test/**` named `*Test/*Tests/*IT`) — a copy/stub of the class under test has no tool to exist, and the sandbox `_NO_NEW` guard wipes any new `.java` except a legit `src/test` test. The **scorer re-running genuine code is the reward-binding mechanism** (today the formulas are advisory/self-reported via the record tools; the tool set already makes `no_cheat` true by construction).

**Rollout rules:** never budget reasoning (P8); never cap a rollout by wall-clock (a truncated trajectory has no clean reward — bound only by internal per-step caps + a stall detector); catch a transient LLM 400 at the `_run_agent` boundary so it doesn't kill the other suspicions' work (P19). Prompts are plain-voice problem-and-reward — no caps/imperatives/checklists.

**Solution search approach and hints:** implementation in the `harness` skill, §P15; the Contract is binding. The v8 ORCH_SYS delegation tree and the earlier four-agent/fact-check blocks are kept as baselines only.

**Reward:** the smallest investigation that proves real bugs with tests, fixes the test-backed ones, and emits a clean review — beating diff-only without cratering.

**Attention mechanism:** a confirm via `grep`/`log` where a test was possible (the reproducer taking the shortcut — its reward still credits grep, the open gap); the solver touching the test (`reward=0`); `investigate_repo` flooding grep-only suspicions on untested code; dedup merging two distinct bugs or dropping a real one; a `cat >`/copy in the probe log (cheat — but first rule out a stale un-truncated prefix); a run dying `exit≠0` (a transient 400 should be caught) or `exit=124` (a wall-clock cap crept back).

---

## P16 — Problem (measurement): a trustworthy per-review score with its evidence on disk.

**Value:** know whether reading the repo helps and at what cost — the evaluation P2 and P11 rely on.

**Contract and constraints** *(operator-only)*: **the judge is CLAUDE, never the reviewer model** — self-grading certifies its own fabrications (Qwen self-judged `sevntu#645` +9 vs Claude −13). Comparison is **3-WAY** (`mr` / `mr_code` / `mr_code_tools`). Metric = code-grounded **POINT judge** with repo access at base (a text-only judge returns `wrong=0` and misses fabrications): per finding good `+1` / critical `+2` / wrong `−1` / trivial `0`, minus `−1` per missed human∪Claude point. Grade on the FULL diff (`full_pr_input`, not the truncated `input`); if the repo is busy, assemble it read-only with `git diff <base>...pr-<pr>-head` (never `checkout`/re-`fetch`, P5). When the protocol changes, RE-MEASURE the whole `n`. Two judges, two jobs: the Claude point-judge is the **quality oracle**; the per-rollout reward is the cheap **execution reward** (P15), with Claude the periodic **auditor** of it (that audit caught the simulation hole). The **200-PR benchmark runs `mode=mr`** (the human oracle is diff-scoped; whole-repo findings = RLVR-only). Run in a few `flock` lanes (polite GPU co-tenant, P18).

**Solution search approach and hints:** implementation in the `harness` skill, §P16; the Contract is binding.

**Reward:** a per-PR net score you can trust, with its trace on disk.

**Attention mechanism:** the protocol changes (token capture, judge, rubric); a `judge=None` hole; the metric misranks a verified-find review; a Qwen-judged number about to be used as a quality claim.

---

## P17 — Problem (verification sandbox): a remote Docker host where a suspicion is proven by EXECUTION, not reading.

**Value:** text tools cannot settle the claims behind our worst errors — wrong-overload/signature, comparator contract, NPE, "won't compile", external-API behavior (the fact-checker once *confirmed* a false Spanner claim it had no way to refute). The compiler/runtime is the exact oracle; running against the REAL classpath turns imagined verdicts into executed ones.

**Contract and constraints** *(operator-only)*: the host is **server2** (`mh` = `mikhailov.tech:2222`, execute-capable, in the `docker` group), a 24-core/125G Linux box that is ALSO the inference host — **never contend for the GPU; builds are CPU/RAM/IO**. Compose with the `bump_java_version` substrate (don't reinvent): deps via its **Nexus** proxy; **untrusted code runs only inside a container**; **bound every probe with an inner `timeout -k`** (a client-side timeout doesn't kill the container) and **cap container logs**. We own only the per-JDK images `review-java-<n>-sandbox` (`n` ∈ 8/11/17/21/25). **Pick the image by the BUILD floor, detected by COMPILING, not the declared `maven.compiler.*`** — a wrong JDK yields false errors that poison the verdict (quarkus#6913: JDK 21 → false `sun.misc` errors; JDK 11 clean). One NAMED container per session (`review-<repo>-<pr>`) mounts BOTH versions — base → `/src/old`, a `pr-<pr>-head` worktree → `/src/new` (cwd `/src/new`) — + warm `~/.m2`; the read surface points at the post-PR worktree so added files are on disk. `reset_clean` (harness-side — the worktree gitdir only resolves there) returns both trees to pristine before each check; the probe log is **truncated per run** (a root-owned stale prefix poisons the copy-cheat audit). Reap worktree + container in `stop()` via a root container, never host `rm`.

**Solution search approach and hints:** implementation/JDK-detection in the `harness` and `detect-java-version`/`bump-java-version-skill` skills (REUSE, don't reinvent); the Contract is binding.

**Reward:** a suspicion's claim is confirmed/refuted by actual `javac`/`java`/`mvn` output; fabrications that pass text-checking fail execution; host + inference endpoint stay within their bands.

**Attention mechanism:** a confirm with no executed evidence; a wrong-JDK false error; a probe/container outliving its run (cache-lock risk); disk/logs creeping full; the endpoint degrading during a build.

---

## P18 — Problem (maintain remote environment): one pinned home on the build host, disciplined disk/cache stewardship.

**Value:** the harness, repo checkouts, dep caches, and sandbox (P17) all share **server2**, which is also the live inference host. Unstable paths, leaked scratch, a runaway container, or a full disk drift the reward's noise floor and can crash the Qwen service we depend on. One pinned home keeps the box reproducible and us a good neighbour.

**Contract and constraints** *(operator-only)*: the project home is **`~/great-java-review`** — the one pinned path; everything else is an env var from `.env`. Docker-bounded: the host is only a Docker host and bind-mount source. **SSH shares one session.** **Inner `timeout -k` on every build/probe** and **cap container logs** (one unbounded log hit 55 GB). Each run **reaps its scratch in a `finally` via a ROOT container** (the build writes root-owned files host `rm` can't) — a surviving `review-*` container/scratch is a reap failure. The host PRUNES images under disk pressure, so **build-on-demand**: rebuild `review-harness` + `review-java-<n>-sandbox` at run start; treat `Unable to find image` as the rebuild signal, not a code error.

**Solution search approach and hints:** pin the home + caches; when disk or the container/scratch count creeps, fix the reap (the leak), don't just sweep.

**Reward:** iteration variance from non-measured factors approaches zero — no disk-full crashes, no stray containers/scratch, the inference endpoint unharmed by our load.

**Attention mechanism:** a `review-*` container/scratch outliving its run; container-log or disk size creeping full; the endpoint degrading during a build.

---

## P19 — Problem (bug fixing): reproduce, root-cause, fix the cause, rerun clean — never a workaround.

**Value:** a bug fixed at its root removes a whole failure class and leaves the code smaller; a guard/special-case hides the cause and accretes cruft. The discipline keeps the harness honest enough to trust its own measurements.

**Contract and constraints** *(operator-only)*: when something breaks — (1) REPRODUCE (a real trace); (2) find the ROOT mechanism, not the symptom; (3) fix the ROOT so the error cannot occur — NOT a `try/except`, "treat as X on failure", retry, or cap that lets the broken path keep running; (4) RERUN CLEAN; (5) clean up the consequences. A workaround is acceptable only as a labelled, tracked stopgap. This is the pipeline's **Solver** (P15) too. **One exception: boundary fault-isolation** — catching a TRANSIENT EXTERNAL fault (a vLLM 400 on malformed tool-call JSON) at the agent boundary so it doesn't destroy unrelated work is tolerance, not masking. The test: does the `try/except` hide a root cause we could fix (forbidden) or isolate an external flake so good work survives (allowed)?

**Solution search approach and hints:** trace on the host before theorising. When a fix ADDS code (a guard/branch/retry), suspect you are masking; the root-cause fix usually REMOVES code (the redundant context, the wrong path).

**Reward:** less code and fewer workarounds after the fix than before; zero masks left in the resolved path; the rerun is clean.

**Attention mechanism:** the diff is the channel — a `try/except` that swallows, a "default to X on failure", a retry around a deterministic error, or a cap that hides an overflow, each signals the symptom was treated, not the cause.
