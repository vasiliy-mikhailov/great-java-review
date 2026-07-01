# AGENTS.md

A delegation protocol, not a checklist. Each entry is a **problem**: one
autonomous concern the operator has offloaded to the agent.

**North star:** find real Java bugs, prove each with a failing unit test, fix
them, and present the find+fix upstream as ordinary human work — the
**suspect → reproduce → fix → synthesize** pipeline (apex **P13**; runtime/
sandbox P10/P15; curation P17). A frozen corpus of real human code-review
comments (P4) is kept as the **benchmark oracle** P14 scores findings against —
the only role human reviews still play.

**The product is a portable skill.** The file-level unit — find → prove → fix
the bugs in ONE Java file — is [`skills/fix-java-bugs/SKILL.md`](skills/fix-java-bugs/SKILL.md):
a pure-LLM, no-runtime-dependency Agent Skill any coding agent can run with just
the build, the JDK, and `git`, WITHOUT this harness. The pipeline is a three-level
descent — **repo → module → file** — where the two upper levels are HARNESS-backed
iteration (open the repo, `repo_map` the modules, hand each module's source files
out one at a time) and the **file level is the skill**. Coverage — every module,
every file addressed — is the harness's guarantee; the bug-work lives entirely in
the portable skill (its own procedure + `0.9^penalty` mergeability rubric, dogfooded
identically in training and production). Everything else here exists to forge and
score that skill, not to be shipped. Modelled on the sibling `java-mutation-testing`
project, whose product is the `improve-mutation-score` skill.

Clustered — meta (P1); discipline (P2–P3); benchmark corpus (P4); substrate
(P5–P8, P15–P16); harness + pipeline (P9–P13); evaluation (P14); curation (P17); target selection (P18); reward improvement (P19).

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
stripped. The file is clustered — meta (P1); discipline (P2–P3); benchmark corpus (P4);
substrate (P5–P8, P15–P16); harness + pipeline (P9–P13); evaluation (P14); curation (P17); target selection (P18); reward improvement (P19).

**Solution search approach and hints:** read → why → intent — for each clause ask
"why is this here?". Strip when the answer is mechanism the agent already fills,
a bare plea for the rule, or an aged enumeration; keep when it scopes when the
rule applies, names a recognition concrete, or signals when to revisit.

**Reward:** cuts that lose words without losing the rule or its scope.

**Attention mechanism:** the file is the channel — an operator edit to a problem's
Contract, or a problem's agent-mutable sections visibly bloating, is the signal to
re-audit.

---

## P2 — Problem (no pre-defense): meet a problem when it occurs, not in advance.

**Value:** speculative armor — a guard, null-check, retry, fallback, or abstraction for a failure that has NOT happened — is dead weight that hides where the code really breaks and multiplies paths no test exercises. Code stays smallest and most honest when every defense answers a failure actually seen. (Seneca: we suffer more in imagination than in reality.)

**Contract and constraints** *(operator-only)*: do NOT pre-defend. Write the direct path; let an unhandled case actually OCCUR — a crash, a real trace — before you guard it, then fix its ROOT (P3), not a blanket mask. No "just in case" null-checks/defaults/retries for inputs that cannot yet arise; no abstraction for a second caller that doesn't exist; no config knob nobody asked for. The bar to ADD a defense is a REPRODUCED failure, not a hypothesis. This is also why we do not pre-LIMIT: a cap, a short timeout, or an output truncation pre-arms against a hypothetical (a slow call, a runaway, an over-large payload) and in practice strangles the real path — set timeouts effectively to infinity (a year), ALWAYS send the FULL data never a truncated tail, and never cap size/depth/reasoning. A limit is a guard you have not earned (kafka#17565's reasoning budget → 26k of noise; an 8000-char output cap once starved the model of the compile error it needed). Complement of P3: P2 is BEFORE the failure (don't pre-arm), P3 is AFTER (root-cause, don't mask). Same single carve-out as P3 — isolating a transient EXTERNAL fault at a boundary so it can't destroy unrelated work; hardening an OBSERVED failure class (keepalive/timeout after a real hang) is met-when-it-occurred, not pre-defense.

**Solution search approach and hints:** if you can't name the trace a guard prevents, delete the guard. A diff that GROWS to handle the imagined is the smell; the direct path is usually smaller.

**Reward:** the direct path shipped; zero guards without a matching observed failure.

**Attention mechanism:** a "just in case" comment; a null-check on a value that can't be null yet; a retry/fallback for a path that has never failed; an abstraction with a single caller "for the future."

---

## P3 — Problem (bug fixing): reproduce, root-cause, fix the cause, rerun clean — never a workaround.

**Value:** a bug fixed at its root removes a whole failure class and leaves the code smaller; a guard/special-case hides the cause and accretes cruft. The discipline keeps the harness honest enough to trust its own measurements.

**Contract and constraints** *(operator-only)*: when something breaks — (1) REPRODUCE (a real trace); (2) find the ROOT mechanism, not the symptom; (3) fix the ROOT so the error cannot occur — NOT a `try/except`, "treat as X on failure", retry, or cap that lets the broken path keep running; (4) RERUN CLEAN; (5) clean up the consequences. A workaround is acceptable only as a labelled, tracked stopgap. This is the pipeline's **Solver** (P13) too. **One exception: boundary fault-isolation** — catching a TRANSIENT EXTERNAL fault (a vLLM 400 on malformed tool-call JSON) at the agent boundary so it doesn't destroy unrelated work is tolerance, not masking. The test: does the `try/except` hide a root cause we could fix (forbidden) or isolate an external flake so good work survives (allowed)?

**Solution search approach and hints:** trace on the host before theorising. When a fix ADDS code (a guard/branch/retry), suspect you are masking; the root-cause fix usually REMOVES code (the redundant context, the wrong path).

**Reward:** less code and fewer workarounds after the fix than before; zero masks left in the resolved path; the rerun is clean.

**Attention mechanism:** the diff is the channel — a `try/except` that swallows, a "default to X on failure", a retry around a deterministic error, or a cap that hides an overflow, each signals the symptom was treated, not the cause.

---

## P4 — Problem (benchmark corpus): a frozen dataset of high-signal human Java reviews — the oracle P14 scores against.

**Value:** the human-review **benchmark oracle** — real PRs with their substantive human review comments, deduped and quality-filtered. P14 scores the pipeline's findings against these as the human ground truth (`−1` per missed human point). Maintained as a measurement baseline, not grown.

**Contract and constraints** *(operator-only)*: `excellent_reviews.json` (23-repo corpus, ~1752 qualifying human-reviewed PRs). A review unit = (PR diff, reviewer, their substantive comments) with LGTM/nits/process filtered out; `dataset.py` reads it for the benchmark. Frozen at its current corpus — if ever regrown, honor the single-GitHub-worker rule (P5) when fetching.

**Solution search approach and hints:** the corpus is frozen; touch it only to fix a quality defect — a misfiltered LGTM/nit that would count as a spurious "missed human point."

**Reward:** the benchmark's human points are clean — no trivia counted against the pipeline.

**Attention mechanism:** a corpus-quality complaint; a missed-point that turns out to be a nit.

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

**Contract and constraints** *(operator-only)*: append-only progress to disk (e.g. `results/*.jsonl`); a flock work-queue (`head_queue.txt`) for parallel lanes that pop atomically; resumable by re-reading state. **Lane count is a RUNTIME KNOB, not a constant:** `head_lanes.max` holds the target, and the self-healing `head_watchdog.sh` reads it EVERY cycle and CONVERGES — STARTS the missing lanes among `1..MAX` while the queue has work, and STOPS any live lane numbered `> MAX` (kills its worker PID + its `review-*-head` container) — so `echo N > head_lanes.max` scales the fleet up OR down live, no restart. The watchdog flags a lane STUCK only when its reasoning-log token stream is silent `> STUCK_MIN` (never kills on a timer; that is the operator's criterion), and prunes images under disk pressure. Long local jobs run under `caffeinate -dimsu` (a closed lid suspends the process and looks like a hang).

**Solution search approach and hints:** make each unit of work idempotent and recorded before/after; a resumed run skips completed units.

**Reward:** an interrupted job resumes with no lost or double work.

**Attention mechanism:** a crash/interruption; work being redone on resume.

---

## P7 — Problem (dependency isolation): no dependency hell.

**Value:** code runs the same on the laptop and the build host, with no version drift.

**Contract and constraints** *(operator-only)*: the working venv (`venv`) stays untouched; the OpenHands harness uses a separate `venv-oh` (Python ≥3.12). Pin SDK versions (OpenHands V1 fields churn). The harness itself runs in a Docker image (`review-harness`) with deps baked but code **mounted** (P10).

**Solution search approach and hints:** separate venvs per concern; pin; never mix the harness env into the working env.

**Reward:** a fresh checkout runs both tracks without a dependency fight.

**Attention mechanism:** an import/version error; an env that only works on one machine.

---

## P8 — Problem (Qwen endpoint): the model under optimization is reachable and bounded-cost.

**Value:** harness/pipeline calls hit Qwen reliably within budget.

**Contract and constraints** *(operator-only)*: OpenAI-compatible `llm_client.py`/`llm.py`; key from `.env` (`QWEN_API_KEY`/`QWEN_BASE_URL`, never committed); Qwen may run concurrently (`qwen.max_concurrency`) — it is NOT the single GitHub worker. **Reasoning ON** (`enable_thinking: true`) for ALL calls — generation, reflection, judges — Qwen is markedly weaker without it. **Never cap reasoning — no `thinking_token_budget`, no small `max_tokens`, no per-turn output throttle.** A reasoning cap doesn't tighten the answer; the model can't think the problem through, **gives up, and emits noise** (kafka#17565 with `thinking_token_budget=2048` → 26k chars of wandering, 0 tool calls). Use the full window (`131072`); `litellm_extra_body` carries `enable_thinking` ONLY. Transport is **streaming** (`stream=True` via a `StreamingLLM(LLM)` subclass) so the read-timeout fires only on a genuinely silent socket, not on a long generation; `num_retries` rides out transient drops. **TCP keepalive is ON on the client socket** (`SO_KEEPALIVE` + `TCP_KEEPIDLE/INTVL/CNT = 30/15/5`): streaming only protects a connection ONCE bytes flow — during a long **time-to-first-token** the socket sits idle with zero bytes and the proxy (Caddy)/NAT reaps it, so the first chunk lands on a dead connection. Keepalive probes hold the idle socket (and NAT/proxy state) across that gap. Wire it where each path actually opens the socket: the single-call path via `OpenAI(http_client=…)`; the harness path (OpenHands **sync** `completion` → litellm `hosted_vllm`, which uses litellm's custom http handler, NOT the OpenAI SDK — so `client_session` is ignored) via **`litellm.sync_transport`** + a client-cache flush. `timeout=None` on the keepalive client so litellm's per-request byte-gap timeout still governs. Same RLVR lesson as the no-wall-clock-cap rule (P13): caps are poison.

**Solution search approach and hints:** lean on `max_concurrency` for throughput; let a rollout finish on its own rather than bounding spend with a cap (P2/P13). Transport-debug detail in the `harness` skill.

**Reward:** endpoint returns 200; per-run cost within budget.

**Attention mechanism:** a non-200; runaway call volume; a reasoning/output cap creeping back in.

---

## P9 — Problem (harness): the loop that lets Qwen read the repo to review.

**Value:** a controllable agent loop that feeds the model the non-MR context (codebase, conventions, API contracts) the pipeline (P13) needs. The assembled machine; its subsystems are P10 (runtime) / P11 (tools) / P12 (compaction) / P13 (topology), and P14 evaluates it. A fix that changes for a subsystem reason lives there, not here.

**Contract and constraints** *(operator-only)*: harness = the **OpenHands V1 Agent SDK** (`openhands-sdk` + `openhands-tools`), NOT the heavy `openhands-ai` monorepo. Loop contract: per-rollout system-prompt override = the genome; score the FINAL artifact only (with thinking extraction); extract the tool trajectory for reflection; point at the thinking-Qwen endpoint (P8); think on; pin SDK versions. **Don't artificially limit the review** — no caps on tool calls, delegation breadth, investigation depth, priority cuts, diff/finding truncation, "write it now" early-stops, or reasoning (P8): a hard limit becomes something the model games (drops content) or gives up on (emits noise). The only bounds are the hard physical ones — the vLLM ceiling (P12), PTY avoidance (P11), a runaway backstop well above real need.

**Solution search approach and hints:** implementation knowledge in the `harness` skill, §P9; the Contract is binding.

**Reward:** a repo-reading review that beats diff-only consistently.

**Attention mechanism:** agent+repo Δ over diff-only going negative on high-base reviews; a context source the pipeline needs but the loop lacks; any one subsystem (P10–P13) dominant.

---

## P10 — Problem (runtime): the harness's execution substrate — reproducible, isolated, right-JDK-per-project.

**Value:** a substrate where the agent's tools can build/run/test the repos, so a hypothesis is verified against execution, without poisoning the signal or contaminating the host.

**Contract and constraints** *(operator-only)*: **the whole harness runs INSIDE a Docker container** (`docker/Dockerfile` → image `review-harness`, launched via `docker/run.sh`; the host Docker socket is mounted so it spawns SIBLING `review-java-<n>-sandbox` probe containers — P15). The repo tree is **mounted** (`-v $PWD:/work`, never baked) and the harness Python is mounted too — **a host edit is the whole deploy, no rebuild**. Qwen creds via `-e`. Dep caches are named volumes (`oh-m2-cache`/`oh-gradle-cache`), warm across PRs. **Untrusted PR code only ever executes inside a container, never the host.** A per-project JDK so a wrong JDK never yields a false compile error (P14/P15).

**Solution search approach and hints:** implementation in the `harness` skill, §P10; the Contract is binding.

**Reward:** any sampled repo builds/tests in a clean container with the right JDK and a warm cache, host uncontaminated.

**Attention mechanism:** a wrong-JDK false failure; a cold-cache blowup; PR code about to run on the host.

---

## P11 — Problem (tools): the tool layer the agent calls — correct, contract-faithful, single-call-useful, no-PTY.

**Value:** each tool does exactly what its description says, in one call, without allocating a PTY.

**Contract and constraints** *(operator-only)*: read tools = `search`/`grep`/`glob`/`file_editor`/`pr_files`/`pr_file_diff`; **NEVER `terminal`** (PTY → `out of pty devices`/`fork failed` at scale → review `0.0`). Every tool's prompt reference must match its registered name; `register_tool` idempotent or the 2nd rollout errors. Outcomes are **CAPTURED BY A TOOL, never parsed from prose** (a prose verdict silently became a lost finding). The write-elsewhere tools of the pipeline (P13), none of which write the host checkout: `add_suspicion` (in-process worklist, runs a dedup subagent); `record_verdict` (verdict + `repro_kind` regression_test|test|log|grep + the reproduction; captures `test_path`/`test_src` read from disk; a verdict reached without a run coerces to `inconclusive`); `record_fix` (the solver's diff + the passing-test rerun); `reset_workspace`; `repo_map`. The reproduce/solve **edit+run** tools live in P13's structural no_cheat set (`run_java`/`edit_file`/`create_test`); arbitrary-bash `sandbox_exec` is retired from those agents.

**Solution search approach and hints:** implementation in the `harness` skill, §P11; the Contract is binding.

**Reward:** every registered tool does what its description says in one call; zero hallucinated-tool errors.

**Attention mechanism:** a `Tool 'X' not found`; `out of pty devices`; a non-idempotent register; a tool returning truncated/misleading output.

---

## P12 — Problem (compaction): context stays BOUNDED and COHERENT across a multi-turn review.

**Value:** the agent never blows the window nor loses the thread to a garbled summary.

**Contract and constraints** *(operator-only)*: token-based compaction (`LLMSummarizingCondenser`). `keep_first` MUST cover the PR message (`keep_first=6`) or the agent synthesizes blind. **INVARIANT:** `condenser.max_tokens + agent.max_output_tokens ≤ max-model-len` — vLLM ERRORS if `prompt + requested_output > 262144`; with output `131072` set `condenser.max_tokens=120000`. The condenser LLM is cloned with `enable_thinking=False`. Tie the two: change one, move the other.

**Solution search approach and hints:** implementation in the `harness` skill, §P12; the Contract is binding.

**Reward:** history never crosses budget; each summary shrinks context and stays factual.

**Attention mechanism:** a summary opening `"Here's a thinking process:"` or larger than what it replaced; a vLLM `prompt + output > model-len` error.

---

## P13 — Problem (topology) **[MAIN / apex]**: the pipeline that finds, proves, and fixes bugs as registry entries.

**Value:** **the project's purpose** — the cheapest agent pipeline that surfaces real bugs, proves each with a failing unit test, and fixes it (then P17 presents the find+fix upstream as ordinary human work) — buying real depth without paying for over-exploration. Delete this and nothing else has a reason to run.

**Contract and constraints** *(operator-only)*: a deterministic **registry pipeline** (`src/current_version/suspicion.py`), each agent given only the tools and the one reward its job needs; everything stored through a tool, never a prose blob (P11). The registry is three linked entry types — **Suspicion → Bug → Solution** — with phase-separated hand-off:
- **Orchestration = repo → module → file (the fix-java-bugs skill, file by file).** `run_suspicion_review` is a DESCENT, not global phases: the harness lists modules (`_modules_with_files`, grouping every `src/main/java/**.java`, tests/generated excluded) and per module iterates the source FILES; each file is one self-contained **find → prove → fix unit** (`_fix_one_file`) — the portable [`fix-java-bugs` skill](skills/fix-java-bugs/SKILL.md) realized with the three agents below, scoped to THAT file's suspicions. Coverage is STRUCTURAL (every module, every file addressed), which retired the whole `0.9^unseen` coverage-reward saga — a *capacity* limit (one context window can't hold netty's 3,524 files; a lone whole-repo agent read only ~101/3,524 ≈ 3%) is fixed by fan-out, not reward-shaping (see P19). Each file proves+fixes its OWN bugs (`max_checks_per_file`, plus a bounded straggler drain for cross-file finds), so there is **no global reproduce cap**. Cost: one find run per source file. `skills/fix-java-bugs/SKILL.md` is the standalone single-agent version of this same procedure (the harness realizes it with three specialized agents; the strict "install the SKILL.md and follow it as one leaf agent" is the sibling java-mutation-testing pattern, a further step). Never a diff (the diff-anchored `investigate_mr` / `INVESTIGATE_MODE` branch was removed 2026-07-01).
- **Investigator → Suspicions (FIND).** `investigate_file` is seeded at one file as an **entrance point**, reads it in full and explores OUTWARD (callers/callees/siblings). A Suspicion = {observation, suspected_bug, location, confidence}; wide net, fire on sight. `add_suspicion` runs a **dedup subagent** (merge into the higher-confidence existing entry; fail-open) — which is what makes per-file fan-out safe (the same bug seen from many entrances collapses to one). **Confidence is the only priority signal** (severity was noise). **`R_suspector = Σ confidence over CONFIRMED suspicions`** — positive-only (a refuted/un-confirmable guess self-zeros), ×0 if nothing confirms so it can't be farmed.
- **Reproducer → Bugs.** Scheduler picks `max(confidence)`. It must SHOW the bug with a **unit test** in the per-PR JDK sandbox (P15): a JUnit `@Test` that fails on the bug — `edit_file` it into an existing `*Test.java`, or `create_test` a new one. `repro_kind` `regression_test` > `test` > `log` > `grep`. Coupled code is reached by **mocking collaborators** (never the class under test: Mockito `mock().thenThrow`/`mockStatic`/`catchSystemExit`/`SecurityManager`); it MAY add `org.mockito:mockito-core` at TEST scope if absent. A verdict is shown BY A RUN or it is `inconclusive`. The **full test scaffolding** is captured **from disk** (authoritative over the paste) — not just the named `test_src`/`build_edit` but EVERY dirty file under any `src/test` tree (`test_files`: helper stubs/mocks/resources too), so the solver can re-materialize all of it into a clean worktree and the test actually compiles (a single-file capture left multi-file tests uncompilable → the solver was forced to touch scaffolding → `test_changed`). What the `@Test` **asserts** must be the genuinely-correct behaviour reasoned from authority (Javadoc/JLS spec, the serialization **round-trip** contract, sibling code) — not the convenient assertion; a test that asserts the wrong expectation (e.g. *throws* where the round-trip says map to a canonical default) proves nothing. **`R_reproduce = no_cheat · ran · shown · 0.9^(mock_loc/covered_loc) · 0.9^(test_loc) · 0.9^(reflection_ops) · 0.9^(inner_classes_loc) + extra_bugs_found`** — the same `base · 0.9^(badness)` shape as the suspector (`0.9^unseen`) and solver (`0.9^LOC`): `ran·shown` MULTIPLY (the test must run AND flip — no partial credit), then the discounts push the proof **small and real-code-driven** — minimal mock vs the production it covers, fewest test lines, the PUBLIC API over reflecting into privates, lambdas over anonymous classes — so the test is *born presentable*, not de-fingerprinted at curation (P17). A test dependency is free (only mock *code* costs); `extra_bugs_found` = other suspicions it raises that confirm, additive and undiscounted. A proven suspicion becomes a Bug.
- **Solver → Solutions.** Separate agent, **only on a Bug that carries a unit test** (grep/log-only bugs are left for the author, not guessed). It re-materializes the test (+ build_edit) into a clean tree and fixes production with `edit_file` + `run_java` until green. **Green ≠ correct:** the same pipeline authored both the test and the fix, so passing only proves they AGREE — it can agree on the wrong behaviour. The solver first reasons what the code SHOULD do (spec/round-trip/siblings) and makes *that* the fix (the green test follows); if the test's expectation contradicts the spec it records `fixed=false` rather than forcing a wrong-but-green change, and prefers the canonical answer (`Locale.ROOT`, not `new Locale("")`). **`R_solve = passes · 0.9^(lines_changed) · test_untouched`** — `passes` = test now passes (no-test bug self-zeros); `lines_changed` MEASURED by git (production only); `test_untouched` = 0 if it changed even one test line (it CAN, the reward says don't — no structural lock).
- **Synthesize → PR.** Reads the registry: each Bug with its test and, when present, its verified fix; `inconclusive` suspicions become hedged open questions.

**no_cheat is structural** (the tool set, not a post-hoc guard): reproducer/solver get only `run_java` (mvn/gradle/java/javac; rejects redirection/write tokens), `edit_file` (str-replace on an EXISTING file), and `create_test` (a NEW file ONLY under `src/test/**` named `*Test/*Tests/*IT`) — a copy/stub of the class under test has no tool to exist, and the sandbox `_NO_NEW` guard wipes any new `.java` except a legit `src/test` test. The **scorer re-running genuine code is the reward-binding mechanism** (today the formulas are advisory/self-reported via the record tools; the tool set already makes `no_cheat` true by construction).

**Rollout rules:** never budget reasoning (P8); never cap a rollout by wall-clock (a truncated trajectory has no clean reward — bound only by internal per-step caps + a stall detector); catch a transient LLM 400 at the `_run_agent` boundary so it doesn't kill the other suspicions' work (P3). Prompts are plain-voice problem-and-reward — no caps/imperatives/checklists.

**Solution search approach and hints:** implementation in the `harness` skill, §P13; the Contract is binding. The v8 ORCH_SYS delegation tree and the earlier four-agent/fact-check blocks are kept as baselines only.

**Reward:** the smallest investigation that proves real bugs with tests, fixes the test-backed ones, and emits a clean review — beating diff-only without cratering.

**Attention mechanism:** a confirm via `grep`/`log` where a test was possible — now `shown=0`, so the reproducer that settles for one earns nothing (the formula closed the old credit-grep gap, but a test left unwritten is still a missed proof); the solver touching the test (`reward=0`); `investigate_repo` flooding grep-only suspicions on untested code; dedup merging two distinct bugs or dropping a real one; a `cat >`/copy in the probe log (cheat — but first rule out a stale un-truncated prefix); a run dying `exit≠0` (a transient 400 should be caught) or `exit=124` (a wall-clock cap crept back).

---

## P14 — Problem (measurement): a trustworthy per-review score with its evidence on disk.

**Value:** know whether reading the repo helps and at what cost — the evaluation P9/P13 rely on.

**Contract and constraints** *(operator-only)*: **the judge is CLAUDE, never the reviewer model** — self-grading certifies its own fabrications (Qwen self-judged `sevntu#645` +9 vs Claude −13). The reviewer is now single-config (whole-repo + tools); the old 3-way `mr`/`mr_code`/`mr_code_tools` context ablation is retired with the diff mode. Metric = code-grounded **POINT judge** with repo access at base (a text-only judge returns `wrong=0` and misses fabrications): per finding good `+1` / critical `+2` / wrong `−1` / trivial `0`, minus `−1` per missed human∪Claude point. Grade on the FULL diff (`full_pr_input`, not the truncated `input`); if the repo is busy, assemble it read-only with `git diff <base>...pr-<pr>-head` (never `checkout`/re-`fetch`, P5). When the protocol changes, RE-MEASURE the whole `n`. Two judges, two jobs: the Claude point-judge is the **quality oracle**; the per-rollout reward is the cheap **execution reward** (P13), with Claude the periodic **auditor** of it (that audit caught the simulation hole). The **200-PR benchmark runs WHOLE-REPO** (the only mode, decided 2026-07-01): **recall = did the whole-repo sweep surface each PR's known bug**, scored by location match against the PR's changed files. Same 200 PRs and same oracle (the PR's real bug), but the sweep is now graded on whether it REACHES that bug amid the whole tree, not on diff review — a harder, more honest recall number. Run in a few `flock` lanes (polite GPU co-tenant, P16).

**Solution search approach and hints:** implementation in the `harness` skill, §P14; the Contract is binding.

**Reward:** a per-PR net score you can trust, with its trace on disk.

**Attention mechanism:** the protocol changes (token capture, judge, rubric); a `judge=None` hole; the metric misranks a verified-find review; a Qwen-judged number about to be used as a quality claim.

---

## P15 — Problem (verification sandbox): a remote Docker host where a suspicion is proven by EXECUTION, not reading.

**Value:** text tools cannot settle the claims behind our worst errors — wrong-overload/signature, comparator contract, NPE, "won't compile", external-API behavior (the fact-checker once *confirmed* a false Spanner claim it had no way to refute). The compiler/runtime is the exact oracle; running against the REAL classpath turns imagined verdicts into executed ones.

**Contract and constraints** *(operator-only)*: the host is **server2** (`mh` = `mikhailov.tech:2222`, execute-capable, in the `docker` group), a 24-core/125G Linux box that is ALSO the inference host — **never contend for the GPU; builds are CPU/RAM/IO**. Compose with the `bump_java_version` substrate (don't reinvent): deps via its **Nexus** proxy; **untrusted code runs only inside a container**; **bound every probe with an inner `timeout -k`** (a client-side timeout doesn't kill the container) and **cap container logs**. We own only the per-JDK images `review-java-<n>-sandbox` (`n` ∈ 8/11/17/21/25). **Pick the image by the BUILD floor, detected by COMPILING, not the declared `maven.compiler.*`** — a wrong JDK yields false errors that poison the verdict (quarkus#6913: JDK 21 → false `sun.misc` errors; JDK 11 clean). One NAMED container per session (`review-<repo>-<pr>`) mounts BOTH versions — base → `/src/old`, a `pr-<pr>-head` worktree → `/src/new` (cwd `/src/new`) — + warm `~/.m2`; the read surface points at the post-PR worktree so added files are on disk. `reset_clean` (harness-side — the worktree gitdir only resolves there) returns both trees to pristine before each check; the probe log is **truncated per run** (a root-owned stale prefix poisons the copy-cheat audit). Reap worktree + container in `stop()` via a root container, never host `rm`.

**Solution search approach and hints:** implementation/JDK-detection in the `harness` and `detect-java-version`/`bump-java-version-skill` skills (REUSE, don't reinvent); the Contract is binding.

**Reward:** a suspicion's claim is confirmed/refuted by actual `javac`/`java`/`mvn` output; fabrications that pass text-checking fail execution; host + inference endpoint stay within their bands.

**Attention mechanism:** a confirm with no executed evidence; a wrong-JDK false error; a probe/container outliving its run (cache-lock risk); disk/logs creeping full; the endpoint degrading during a build.

---

## P16 — Problem (maintain remote environment): one pinned home on the build host, disciplined disk/cache stewardship.

**Value:** the harness, repo checkouts, dep caches, and sandbox (P15) all share **server2**, which is also the live inference host. Unstable paths, leaked scratch, a runaway container, or a full disk drift the reward's noise floor and can crash the Qwen service we depend on. One pinned home keeps the box reproducible and us a good neighbour.

**Contract and constraints** *(operator-only)*: the project home is **`~/fix-java-bugs`** — the one pinned path; everything else is an env var from `.env`. Docker-bounded: the host is only a Docker host and bind-mount source. **SSH shares one session.** **Inner `timeout -k` on every build/probe** and **cap container logs** (one unbounded log hit 55 GB). Each run **reaps its scratch in a `finally` via a ROOT container** (the build writes root-owned files host `rm` can't) — a surviving `review-*` container/scratch is a reap failure. The host PRUNES images under disk pressure, so **build-on-demand**: rebuild `review-harness` + `review-java-<n>-sandbox` at run start; treat `Unable to find image` as the rebuild signal, not a code error.

**Solution search approach and hints:** pin the home + caches; when disk or the container/scratch count creeps, fix the reap (the leak), don't just sweep.

**Reward:** iteration variance from non-measured factors approaches zero — no disk-full crashes, no stray containers/scratch, the inference endpoint unharmed by our load.

**Attention mechanism:** a `review-*` container/scratch outliving its run; container-log or disk size creeping full; the endpoint degrading during a build.

---

## P17 — Problem (curation): an upstream PR presents Qwen's find AND fix, never the agent's invention.

**Value:** the experiment's claim is that **AI-found-AND-fixed** bugs land on their merits — now presented transparently, with the AI-assistance disclosure included (see the Contract), not as undisclosed human work. If the agent re-derives the test or the fix, the PR silently degrades to "Qwen found, Claude fixed" — a weaker and dishonest claim. The registry already holds Qwen's whole artifact set; the curating agent's job is to PRESENT it, not to author.

**Contract and constraints** *(operator-only)*: every upstream PR is built from Qwen's registry entries **FIRST, in this order of source** — the **Suspicion** (the bug + location), the **Bug**'s `test_src`/`test_files` (the regression test), and the **Solution**'s `fix_diff` (the production patch, `fixed=true`, proven by `fix_rerun`). Take Qwen's four artifacts — suspicions, bugs, tests, solutions — AS WRITTEN; the agent does NOT substitute its own suspicion, test, or fix as the default. The agent may offer its OWN **only when Qwen's is genuinely BAD** — missing (no `fixed=true` solution / `validation:None` / no test), wrong (wrong-but-green, asserts a non-spec behaviour, or embeds a copy of the class under test instead of calling the real one), or un-PR-able (no real caller; private method with no real-class test) — and even then the agent's substitute is **SHOWN and used ONLY AFTER explicit human acceptance**, never silently. Regardless of source, still **prove red→green by EXECUTION** (P15) before opening, and honour P5 (**include the standard AI-assistance disclosure — the block below — in every upstream PR body**; explicit operator go for ASF/`apache/*`; spread across maintainers, don't flood one; check own open PRs first).

**Body shape: a debugging story, not a form** *(2026-06-30)*: present the find+fix top-to-bottom the way the programmer who just debugged it would write it up — (1) the **failing test FIRST** as the reproduction, with `// arrange` / `// act + expect` comments so it reads "I set up this situation, called that, expected this"; (2) **got** — the trimmed captured failure (`bug_trace`); (3) the **root cause IN the real code** — paste the few buggy lines and point at them, not prose about them; (4) the `fix_diff` + ONE line on why it is the minimal cause-fix (e.g. "it only needs those tables to decide whether to reload, so capture the reference before dropping"); (5) **green now** — red→green condensed to the line that moved (`Failures: 1 → 0`), full before/after logs in a `<details>`. The reviewer walks the path you walked, so nothing needs explaining. **No mechanical field-table** (`call / expected / actual / reason / fix`) — it reads as a form and makes the reviewer parse, the opposite of don't-make-me-think. The skeleton is mechanical from the registry (location, `test_src`, `bug_trace`, `fix_diff`); the arrange/act/expect labels and the why-minimal sentence are the human touch that makes it read *debugged*, not generated. **Set the body ONCE at open time — never retro-edit an opened PR** (notification churn for the maintainer).

**Paste the verification trace — don't make the reviewer imagine it** *(since 2026-06-27)*: a reviewer should never have to mentally simulate "could this bug really be true?". Every upstream PR's `## Verifying this change` section MUST show the **actual captured console output** of the regression test failing on the unpatched code and passing with the fix — the real surefire/gradle summary lines plus the specific failure message (`expected: false but was: true`, `ArithmeticException: / by zero`, the `Class:line` of the assertion), then the green `Tests run: N, Failures: 0` + `BUILD SUCCESS`. Format as two fenced blocks labelled "Before the fix (on current `<base>`)" and "After the fix". The bug+test+fix together are unconvincing as prose; the failing-then-green trace is the proof that removes the imagination.

**Trim framework noise when pasting (not at capture)** *(2026-06-28)*: the stored trace keeps every `at …(:line)` frame, so a Maven/JUnit failure carries ~20 lines of framework plumbing (`at org.junit.runners.*`, `at org.apache.maven.surefire.*`, `at java.base/*`). Leave the capture raw; when curating the PR body, DROP those framework-internal frames and keep the assertion/exception message, the project's own frames, and the `Tests run`/`BUILD` summary. (Gradle output is already compact.)

**These two traces are PIPELINE ARTIFACTS, not something to re-run per-PR** *(2026-06-27)*: the Reproducer captures the failing run as `bug.bug_trace` (the AUTHORITATIVE last `run_java` where the test went red — `Tests run … Failures: >0`) and the Solver captures the green run as `solution.fix_rerun` (the last `run_java` with `Failures: 0, Errors: 0` + BUILD SUCCESS). Both are read off genuine tool output, never the model's prose, and the **reward is gated on them** — a confirm with no captured red run downgrades to inconclusive, a fix with no captured green run scores 0. So PR curation PASTES `bug.bug_trace` (before) and `fix_rerun` (after) straight from the registry; **never paraphrase, approximate, or fabricate a trace**. Only re-run by EXECUTION (P15) if a trace is missing/stale for a repo whose verification you redid by hand.

**Standard AI-assistance disclosure** *(PROACTIVE / default-on since flink#28557, 2026-06-27 — reverses the earlier silent no-attribution stance after reviewer @spuru9 asked for it)*: add a `## AI assistance disclosure` section to **every** upstream PR body, this text verbatim — *"This contribution was produced with the help of an AI pipeline. The pipeline processed a large amount of source code to surface suspected bugs, reproduced a subset of them with failing unit tests and generated candidate fixes, and prepared pull requests from the ones that held up. Each PR was then reviewed and verified by a human before being opened: the fix and test were checked by hand and the test was confirmed to fail before the change and pass after."* Keep it honest and non-overclaiming — no inflated specific counts. The find+fix is still Qwen's and the human review is still real; disclosure adds transparency, it does not change either.

**Pre-open guards (run `pr_preflight.py`):** the SELECTION factor is the **maintainer's conduct toward contributors**, not their AI stance — is dealing with this person net-positive or net-negative for the operator's standing? Three checks before every PR, none a hard block (warnings the operator weighs):
1. **Maintainer screen** *(the gate)* (`pr_preflight.py maintainer <repo>`): profile the active maintainer's recent public interactions. ENGAGE repos whose maintainers review fairly, thank reporters, and merge; **AVOID** the ban-prone / shaming / "spam"-dismissing ones (akarnokd banned `bhja` for merely over-asking, and us for undisclosed AI — both reputation-negative to tangle with, regardless of merit). An AI-policy clause is a **footnote, not a veto**; the CLA/DCO it surfaces still must be signed to merge.
2. **Idiomatic PR** (`pr_preflight.py tells` + the **repo's own formatter** on every touched file): lambdas not anonymous inner classes; no narrating comments; a terse, **em-dash-free** PR body/commit; if the formatter rewrites the file it was not conforming (format, never hand-splice — the `@Test`-indentation tell came from gluing). This is PR quality every decent maintainer appreciates, not concealment.
3. **Engage**: an opened PR is **monitored and answered**; fire-and-forget is forbidden. The contrast cases (gson/druid/keycloak) landed on merit because the maintainer was respectful AND someone responded.

**Solution search approach and hints:** the fix lives in `registry.solutions[].fix_diff` (NOT the susp_runs top level — `solved` is only a count); join `solution.bug_id → bugs.id` for the location + `test_src`/`test_path`. Target the **solved set** (`fixed=true`), not the raw suspicion list. Apply `fix_diff` by replicating its exact change; reuse `test_src` verbatim. Skip archived/deprecated target repos (easyexcel, fastjson). Where Qwen has no artifact, FLAG the gap and wait — do not quietly fill it.

**Reward:** every merged upstream PR is provably Qwen's find+fix; the agent's authored content is the rare, human-approved exception, logged as such.

**Attention mechanism:** a PR whose fix or test the agent wrote without a human OK; a "cleaner" rewrite of Qwen's `fix_diff` (the easyexcel `rowCache.size()` vs Qwen's `lastRowIndex + 1` trap); opening before red→green; an archived/deprecated target repo; re-deriving when a `fixed=true` solution was sitting in the registry.

---

## P18 — Problem (target selection): pick repos by predicted maintainer-acceptance, not stars.

**Value:** the pipeline is only worth the merges it lands. A PR into a barren enterprise is wasted effort (polite silence) and a PR into a hostile gatekeeper is a public shaming that taxes the whole experiment (P5). Star count picks neither well — it tracks reach, not *whether a stranger's fix gets merged*. Choosing the corpus by **predicted acceptance × reach** instead of stars is the cheapest lever on realized merges.

**Contract and constraints** *(operator-only)*: a transparent predictor `maintainer_accept.py` scores any `owner/repo` on **TWO axes — merge yield × reputational risk** — from cheap GitHub signals, emitting `P(merge)`, `reputational_risk`, a `recommendation ∈ {TARGET, CAUTION, SKIP}`, and a `selection_score = P(merge) · reach`. Three buckets, calibrated to the field rates: **foundations / true multi-maintainer** (Apache, Eclipse, DSpace, dkpro; or any org with a broad committer base) ≈ 75% merge, zero hostility → **TARGET**; **solo maintainers** ≈ a coin-flip on merge and the source of every shaming → **CAUTION**; **enterprises** (AWS, Liquibase) safe but barren, ~0 external yield → **SKIP**.

The core theory: **single-maintainer is ENDOGENOUS, not circumstantial.** A popular, old, much-forked repo with many would-be contributors that is *still* single-maintainer is solo by **revealed preference** — a maintainer who kept sole merge authority — and that same disposition rejects (and shames) a stranger's PR. They are single not for lack of a partner. So the predictive feature is not team SIZE but the **GAP between the OPPORTUNITY to have grown a team** (`stars`, `age`, `forks`, distinct would-be contributors who already tried) **and the REALIZED team** (distinct recent committers, top-committer share): **deliberate-solo** (high opportunity ∧ still solo — `stleary/JSON-java` 4.7k★/15y, `redisson` 24k★/Nikita-90%) → the **shaming tail** lives here; **incidental-solo** (small/young, solo by circumstance — a 25★ niche appender) → low downside. The gap governs the **reputational-risk axis, NOT P(merge)**: the 200-PR backtest found deliberate and incidental solos merge at the SAME coin-flip rate (~50% each) — a red→green-verified PR is merged even by a gatekeeper — so the gap RISK-ADJUSTS selection (`selection_score = P(merge) · reach · risk_factor`) rather than lowering the yield estimate. The same opportunity that makes a deliberate-solo a shaming risk makes a project that *realized* it (`netty` 35k★ **and** 30 committers, emr 0.98) the sweet spot.

The strongest single signal is the **external-PR merge rate** (of the last ~50 closed PRs by non-members, the fraction merged) — direct yield; the `/pulls` list omits `merged_by`, so realized-team is read from the last ~100 commits, never from who-merged. The predictor is **calibrated against our OWN PR history** (the merged/closed corpus is the labelled oracle; `yakovenkoalg-collab` self-merges excluded): TARGET must hold ≈ 75% precision, SKIP ≈ 0 accept, CAUTION ≈ coin-flip. The opportunity gap is validated on the RISK axis, not the merge axis — the sample shows no merge-rate difference between deliberate and incidental solos (~50% each), consistent with high-quality PRs landing even with gatekeepers; the gap's real claim — deliberate gatekeepers carry the **shaming tail** — must be tested by classifying CLOSED PRs hostile-vs-polite, NOT by merge rate. This problem **gates the corpus P13 runs on** (don't burn the pipeline hunting bugs in a repo that won't merge) and **feeds P17** (never open into a SKIP; treat CAUTION as "only an impeccable, well-scoped PR"). It is maintainer-respect made selective, NOT an AI-policy screen.

**Solution search approach and hints:** `maintainer_accept.py owner/repo [--json]`; the 200-PR self-outcome backtest is the calibration oracle — re-fit the bucket priors and the opportunity thresholds when the corpus grows. Rank candidates by `selection_score`, pick the top-N biased to TARGET. A single PR per repo is a noisy label — trust the aggregate buckets, not one outcome.

**Reward:** a calibrated `P(merge)` and a target list whose realized merge rate beats stars-only, with zero PRs spent on barren or hostile repos.

**Attention mechanism:** a repo chosen on stars alone; a speculative PR about to land on a deliberate gatekeeper (popular, old, still single-maintainer — shaming risk); effort spent on a barren enterprise; TARGET precision drifting below ~70%, or the CAUTION bucket failing to split on the opportunity gap.

## P19 — Problem (reward improvement): each pipeline reward's argmax equals the wanted outcome, climbed in a Ralph loop.

**Value:** every agent in P13 optimizes EXACTLY the reward it is handed, so a mis-shaped reward silently caps the whole pipeline and no prompt-polish elsewhere recovers it. The rewards ARE the genome (prompts are what GEPA tunes, P13); a reward that vanishes, saturates, or is farmable trains the wrong behaviour while reading fine on the page. This is the loop that keeps each reward's argmax equal to the outcome we actually want (real bugs found-and-fixed, broad coverage), judged by measurement (P14), not by how good the reward *sounds*.

**Contract and constraints** *(operator-only)*: a reward is a GUIDELINE the model climbs whether or not a scorer runs after it — so a reward change is a **prompt** change first (the `Your score:` block of the investigator/reproducer/solver system prompts) and, when a runtime scorer exists, it must state the SAME formula. Reward shapes obey three laws or they mistrain: **bounded dynamic range** — never a raw COUNT whose exponent grows with repo size. `0.9^(unseen files)` does NOT literally vanish at netty scale (`0.9^3423 = 2e-157` is representable, and GRPO normalizes absolute magnitude); the real failures are (a) its within-group log-range (~7 across a 70-file spread) DOMINATES the bug-signal (~1.6) ≈4.6:1, training the agent to read over finding, and (b) it underflows to a true 0 past ~6,740 files. Prefer a fraction / bounded exponent — but note the worked resolution here was NOT a reward reshape: coverage was a CAPACITY limit (one window can't hold 3,524 files), fixed STRUCTURALLY by one-investigator-per-file (P13), which is why the coverage term is gone entirely. **un-farmable** — multiplicative `×0` on the real outcome, so effort/coverage alone can't bank score; **gradient toward the goal** — marginal reward strongest where the agent should go (finishing, not merely starting; `0.9^(1/f)` fails this — it saturates). The meta-lesson: check whether a shortfall is a reward problem at all before reshaping — a capacity/architecture limit wears a reward mask but isn't one. Claude is the quality oracle, never Qwen self-judged (P14). The autonomous optimizer (GEPA `gepa_run`) is OFFLINE (excised with mimicry 2026-06-25), so this loop is **hand-run**: propose → synth-smoke → measure → tune → repeat; re-standing an autonomous optimizer (v9: reward = Claude point-net quality) is itself a move under this problem.

**Solution search approach and hints:** for each reward ask "what does an agent that MAXIMIZES this literally do?" and find the degenerate answer (read 3% and stop; assert-false; touch the test) before trusting the words. Plot the shape over the REAL range (a 3,524-file repo AND a 60-file module) — if the gradient is flat where the goal is, reshape (bound the exponent, raw-count→fraction, move the penalty to the achievable unit). One reward at a time; change the prompt AND this file's Reward clause together; validate on the synth-smoke (it must still find-and-fix the planted bug) before any real run, and read the AGENT JOURNEY (what the model actually did under the new wording), not just the number.

**Reward:** each pipeline reward's argmax provably equals the wanted outcome — P14 quality rises after a reward change, with no farming and no synth-smoke regression.

**Attention mechanism:** an agent doing far less than its reward "says" (reads 3% under a read-everything reward → broken gradient); a reward written as a raw COUNT that scales with repo size (vanishing risk); a path to bank score without the real outcome (farmable); a reward edited without a smoke or without reading the agent-journey; measured quality flat or down after a reward change.
