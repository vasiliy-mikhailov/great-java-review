# Pipeline regression tests

TDD regression suite for the **reward genome** (`src/current_version/suspicion.py`, `sandbox.py`,
`pr_diff_tool.py`, `search_tool.py`) — the code that actually trains the model. Each test pins a
defect from the pipeline code review fail-before / pass-after; the fixes followed the tests.

## Run

```bash
cd current_attempt
PYTHONPATH=src:tests venv-oh/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

(`venv-oh` is the pipeline's Python 3.12 env — it has the OpenHands SDK that `suspicion.py`
imports. No pytest needed: these are stdlib `unittest`. No Docker / no Qwen / no network — the
sandbox boundary is faked, so the suite runs in well under a second.)

To run one finding's tests, e.g. `PYTHONPATH=src:tests venv-oh/bin/python -m unittest test_flip_reset -v`.

## Layout

`_fakes.py` — shared base case (`PipelineTC`: resets the process globals `_RUNS`/`_STORE`/
`_VERDICT`/`_FIX` and restores the sandbox handle + env around every test; `patch_attr` for
auto-restored monkeypatches) and `FakeSandbox` (an in-memory, scriptable stand-in for the Docker
sandbox, with real temp worktrees so scaffold read/write works). Build-output fixtures for Maven /
Gradle / JUnitCore live here too.

| test file | findings | what it pins |
|---|---|---|
| `test_no_cheat.py`      | **C1**, L7        | run_java rejects newline/cp/mv/rm second statements; `_is_test_path` can't be traversed out of `src/test` |
| `test_flip_reset.py`    | **C2**, **H1**    | the flip resets to pristine + re-materializes the test before running; judges by trace, not raw exit codes |
| `test_trace_binding.py` | **C3**, M5, root-cause B | before/after proof traces are bound to the bug's OWN test; `fix_rerun` is never model prose |
| `test_trace_classify.py`| L5 (+ H1 half)    | `_trace_shows_fail`/`_trace_shows_pass` across Maven/Gradle/JUnitCore; compile-fail ≠ test-fail; UP-TO-DATE ≠ pass |
| `test_dedup.py`         | M2, M3            | a confidence bump reaches the scheduler; free-text mentioning a number doesn't false-merge |
| `test_jdk.py`           | M4                | Gradle `JavaVersion.VERSION_1_8` (and the 1.x form) is detected, not defaulted to 21 |
| `test_reward_math.py`   | L3                | `diff_numstat` counts `max(added,deleted)`, not the doubled `added+deleted` |
| `test_timeout.py`       | M1                | `exec_` defaults to a large timeout (env-overridable), not the 120s wall-clock cap |
| `test_misc.py`          | L1, L10, L11      | solver is wired `edit_code`; `pr_files` resolves renamed paths; search hint drops retired `sandbox_exec` |

## Accepted residuals (by design, not bugs)

An adversarial audit of the fixes flagged these; left as deliberate trade-offs:

- **Trace binding favors recall-safety over a whole-module Gradle run.** A fix proven by `./gradlew :mod:test`
  with no `--tests` won't bind (Gradle prints no per-test class name on pass, so the selector isn't found) →
  scores 0. This is a false-negative (lost credit), never a false-positive (gamed reward), and the
  reproducer/solver prompts already direct named runs (`-Dtest=…` / `--tests …`), which bind correctly —
  including JUnit5 `@Nested` (`-Dtest='Outer$Nested'`).
- **`exec_` default timeout is 7200s (2h), not literally "a year" (P2).** Tension with P6 (the container must
  self-bound or it holds cache locks forever). 2h clears any scoped `-pl/-Dtest` probe; raise it with
  `SANDBOX_EXEC_TIMEOUT_S` for a whole-reactor build.
- Review findings **L2, L4, L6, L8, L9, L12** were note-only in the review and remain unfixed here.

## End-to-end

These are unit + orchestration-level (FakeSandbox) tests. The full live end-to-end harness is the
existing `./synth_smoke.sh` (planted-bug repos, real Qwen + Docker, run on `mh`) — run it after a
genome change to confirm the plumbing end to end before a real repo.
