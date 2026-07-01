---
name: fix-java-bugs
description: "Find and fix real bugs in a Java (Maven or Gradle) file: read one source file, prove each suspected bug with a test that FAILS on the current code, then fix the ROOT CAUSE so the test passes, never a workaround. Use when asked to find and fix bugs in Java code, review a Java file for defects and fix them, or harden a class against a bug you suspect."
---

# Fix real bugs in a Java file

Reading code for bugs is cheap and unreliable; a **test that FAILS on the bug and goes GREEN on your fix** is proof. This skill turns one source file into *proven, fixed* bugs: read the file, spot a concrete defect, write a test that fails because of it, remove the ROOT CAUSE so the test passes, and leave the suite green. A suspicion you cannot make a test fail on is a guess — you drop it, you do not ship it.

Work on **one file at a time** (its "entrance point"), exploring outward only as far as a bug needs. Standard tools only: the build, the matching JDK, `git`.

**The reward you maximize: +1 for every real bug you PROVE (a failing test) and FIX (that test now green, at the root cause), with no existing test weakened.** A suspicion no test can make fail scores 0; a "fix" that masks the symptom instead of removing the cause scores 0. Drive it with the loop in §5.

## 0. Preconditions
- **Detect and use the right JDK FIRST**: follow the `detect-java-version` skill. A project's real build floor can exceed its declared target, and the wrong JDK yields false compile errors. Determine the JDK, then run EVERY command below under it.
- **Detect the build tool:** root `pom.xml` → Maven; `build.gradle`/`.kts` (+ `gradlew`) and no `pom.xml` → Gradle. Use the project's wrapper when present (`./mvnw`, `./gradlew`).
- **Green baseline.** Your new test's RED must be caused by the bug, not a pre-broken suite. Confirm the module compiles and the tests you'll touch are green first; tests already red for infra reasons (DB/network/Docker) are not your concern — scope around them.
- **Detect the test framework and version FIRST**: follow the `detect-unit-testing-framework` skill (JUnit 4 / 5 / 6 / TestNG, resolving `${...}`/BOM version indirection). It decides where and how you add the proving test.
- `git`: commit a baseline first, so your fix + test are an isolated diff.

## 1. Read the one file, in full
- You are handed ONE file `F` (the entrance point). Open it **completely** and read it — not a skim.
- Follow outward only as a bug needs it: the classes `F` calls, its callers, a sibling that shares a pattern. You do NOT survey the repo; another run enters from every other file, so cover `F` and its immediate neighbourhood well rather than wandering.
- Note the module `F` lives in (`.../src/main/java/...`) and its test root (`.../src/test/java/...`) — that is where the proving test goes and what the build (`-pl <module>`) scopes to.

## 2. Find the suspected bugs: concrete, seen-in-the-code
Read `F` for **defects you can point a finger at**, not vibes. The richest kinds:

| Smell | Example |
|---|---|
| wrong comparison / boundary | `>` where `>=` is meant; an `index > size` guard that lets `index == size` through |
| copy-paste slip | a branch that returns or uses the wrong field, or a sibling's value |
| off-by-one | `i > 0` skipping index 0; `get(n-1)` after an `n >= size` check |
| broken contract | `equals` not symmetric; `compareTo` casting a `long` diff to `int` (overflow); `hashCode`/`equals` disagreeing |
| resource leak | a stream / lock / buffer not released on every path, especially the exception path |
| mishandled edge case | empty / `null` / single-element input throwing where it should return; negative / overflow / unicode |

Record each as **observation** (the exact line and what is wrong), **suspected_bug** (the behaviour it causes), **location** (`F:line`). Do NOT flag style, naming, formatting, or "could be cleaner" — only a defect a maintainer would call a bug. Cast a wide net: a missed bug is gone for good, an extra suspicion costs only the proof attempt in §3.

## 3. Prove it with a failing test (or drop it)
A bug is real only when a test SHOWS it. For each suspicion:
- Write a `@Test` that **asserts the genuinely-correct behaviour the bug violates** — reasoned from the Javadoc, the JLS, a round-trip / `equals` / `compareTo` contract, or a sibling method — so it goes **RED on the current (buggy) code**. Arrange the exact input, act, assert the expected value; the failure message is the "expected X but got Y" that names the bug.
- Add it to the existing `*Test.java` for the class, or create one under the module's `src/test/java`. **Assert the CORRECT behaviour, never the bug's wrong output** — a test written against the current wrong value is green immediately and proves nothing.
- If the code is coupled (needs a client, DB, I/O, or an exception path), **mock the collaborators** — Mockito `mock().thenThrow`, `mockStatic`, a `SecurityManager` / `catchSystemExit` for `System.exit` — never mock the class under test. You may add `org.mockito:mockito-core` at **test scope** if absent.
- Run just that test. It must fail **for the reason you predicted** (read the assertion error, not just the red). A suspicion you cannot turn red — because the behaviour is actually correct, or you cannot reach it — is **not a bug**: drop it, say why, move on. Do not ship an unproven suspicion.

## 4. Fix the ROOT CAUSE, not the symptom
Make the failing test pass by removing the **cause**:
- Correct the wrong operator, the off-by-one guard, the copy-pasted field, the leaked-resource path — the actual defect. A root-cause fix usually **corrects or removes** a line; it rarely adds one.
- **Never** a `try/catch` that swallows, a "default to X on failure", a special-case branch, or a cap that lets the broken path keep running. That masks the bug and scores 0 here (rule 1).
- Keep the diff **minimal** — the fewest production lines that make the test green and the class correct. No drive-by refactors or reformatting.
- Re-run the test (now GREEN) **and the module's existing tests** — your fix must not break another. If it does, you fixed the wrong thing, or a sibling test encodes the bug; reconsider before overriding it.
- **Green ≠ correct.** You wrote both the test and the fix, so passing only proves they *agree* — they can agree on the wrong behaviour. Sanity-check the fix against the spec / siblings: is this what the code SHOULD do? If the correct behaviour is genuinely ambiguous, assert the spec answer and note the ambiguity rather than forcing a convenient one.

## 5. The Ralph loop + when to delegate
Treat §2 → §3 → §4 as one loop body per bug, and repeat until the file is clean:

```
loop:
  pick the next suspected bug (surest first)
  write the failing test (§3)      -> won't go red for the right reason? it is NOT a bug: drop it
  fix the root cause (§4)          -> that test GREEN and the module's tests GREEN
  reward += 1 for this proven+fixed bug
  re-read F with the fix in mind   -> did the fix reveal (or mask) another? add suspicions
  no suspicion left that can be made to fail  -> run §6, then STOP
```

**More than ~2-3 suspected bugs in `F`, or `F` is large? You are the FILE-MANAGER: delegate one bug at a time, do NOT prove+fix them all in your own context.** Proving and fixing several bugs in one conversation piles test output, source, and diffs into one window until an edit is cut off mid-write (a broken file, a red build). Give each bug its own fresh context.

Delegate with your environment's sub-agent / task tool (an OpenHands `task`, a Claude Code Task). Pick a sub-agent that can **edit files and run tests** — not a read-only explorer, which reads and writes nothing. Your tool may warn "do not delegate edits, use the editor directly" — that default does NOT apply here: per-bug prove+fix is exactly what you delegate, because a multi-bug file does not fit one context. One at a time, **SEQUENTIAL** (parallel sub-agents collide on the shared test file and the production file). Brief each:

> Prove and fix ONE bug in `F` (module `<mod>`, JDK `<jdk>`): `<observation + suspected_bug + location>`. Write a `@Test` in `<TestClass>` that asserts the CORRECT behaviour and so FAILS on the current code (mock collaborators if needed; you MAY add mockito at test scope). Then fix the ROOT CAUSE in production — never a guard / try-catch / workaround — minimal diff, until that test is GREEN and the module's tests still pass. If the suspicion cannot be made to fail for the right reason, report NOT-A-BUG with why. Report back SHORT: the `@Test` name, the one-line fix, red→green confirmed, module green. Never paste raw build output — distill it.

You do not touch `F` or the test file yourself between delegations. When every bug is done, run the module's tests ONCE to confirm all green, then §6.

## 6. Mergeability reward: a green fix a maintainer won't merge scores nothing
A passing test proves the bug; it does not make the change **mergeable**. Have a **separate judge sub-agent** — one that did not write the fix and shares none of your context — score the diff against the rubric (grading your own work while driven to finish inflates it). Pure-LLM, no install: the judge is just a fresh model applying the rules. **reward = 0.9 ^ (penalty)**, where penalty = the total number of LINES of bad code across every rule (an offending method counts its whole body; a per-line wart counts its matching lines), so a one-line slip barely dents the reward and a warty method tanks it. `1.0` = nothing broken. Count only the lines YOU added or changed, against the baseline.

| # | rule | broken when (penalty = offending lines) |
|---|---|---|
| 1 | root-cause | the production change MASKS the symptom (added `try/catch`, null-guard, default-on-failure, special-case, cap) instead of removing the cause: **binary** |
| 2 | minimal-diff | production lines changed beyond what the fix needs — refactors, drive-by edits, reformatting |
| 3 | test-asserts-correct | the test asserts the buggy behaviour, or asserts nothing real (`assertDoesNotThrow`-only / coverage theatre) |
| 4 | api-only | the test reaches internals via reflection (`setAccessible`, `getDeclaredField`, `ReflectionTestUtils`, `Whitebox`); drive the public API |
| 5 | no-weaken | edits, deletes, or relaxes an existing test or assertion (penalty = touched lines); the regression test is append-only |
| 6 | deterministic | `Thread.sleep`, unseeded `new Random()`, wall-clock, real network / file IO in the test |
| 7 | green | the test or the module does not compile / is red: **binary** |
| 8 | real-bug | the "bug" is actually intended or documented behaviour, so the fix changes correct code: **binary** |
| 9 | no-comment-spam | standalone comment lines out-pace code more than 1 per 4; comment *why*, not *what*; no comment that hardcodes a line number or names the tool |
| 10 | repo-idiomatic | test or fix do not match the module's conventions — read CONTRIBUTING and one sibling test first (assertion library, naming, given/when/then); penalty = diverging lines |

**Part of the §5 loop, not a final gate.** Each pass, once green, re-judge and fix every broken rule **without dropping the kill** — rewrite the fix to be root-cause, the test to use the public API, and so on. Never weaken the proof to clear a rule; if a rule genuinely cannot be met without losing the fix, keep the fix and record the residual. Stop at reward `1.0`, not at "green".

> **Contract: no runtime dependency.** This skill is just `SKILL.md` — no script, nothing to install. The reward above is your own line-counted judgment against the rubric, so it works in any environment (opencode, kilocode, CI, a bare editor) with no Python. The rubric is the contract; you score against it directly.

## 7. Not-a-bug is common — prove before you fix
A suspicion is a bug only if a test FAILS on it for the right reason. Many plausible reads are the code's **intended** behaviour: a documented contract, a deliberate edge-case choice, a sibling that relies on it. Before you change anything, make the test go red **and** confirm the behaviour is wrong against an authority (Javadoc, the JLS, a round-trip / `equals` / `compareTo` contract, a sibling). If you cannot make it fail, or the "correct" behaviour is really the current one, **drop it and say so** — a fix to correct code is a regression, and it fails rule 8. Cast wide in §2, but only ship what §3 turned red.

## 8. Open a PR
Open a PR only once §6 reward is `1.0` (or the only residual is one you documented as unremovable without losing the fix). Branch, commit the **root-cause production fix + the append-only regression test** as one isolated diff, and open a PR whose body shows the bug as a failing test (arrange / act / expected-vs-got), names the root cause in the real code, and shows red → green. Always end the body with a short **How this was produced** disclosure: an AI-assisted pipeline that finds a suspected bug, proves it with a test that fails on the current code, and fixes the root cause so the test passes — every fix backed by a regression test. Disclose the AI methodology explicitly; never omit it.

---

## Gotchas
- **A fix that ADDS code is a smell.** Root-cause fixes usually correct or remove a line (the wrong operator, the bad guard). If your diff grows a `try/catch` or a null-check, you are probably masking — re-find the cause.
- **The test must fail for YOUR reason.** A test red because it does not compile, or because of an unrelated infra failure, proves nothing. Read the assertion error; it must be the "expected vs got" of the bug.
- **Do not assert the bug.** The commonest mistake: writing the test against the current (wrong) output so it is green immediately. The test must assert the CORRECT behaviour and start RED.
- **Green baseline before you touch anything.** If the module's tests are already red (a too-new JDK false error, a missing profile), fix the environment first (see `detect-java-version`) or you cannot tell your RED from the pre-existing one.
- **Mock infra, do not stand it up.** A bug on an exception / IO / coupled path is proven by mocking the collaborator (`when(dep...).thenThrow`), not a real DB / Redis / network. Never mock the class under test.
- **Give build / test commands a HUGE timeout** (~1 year, e.g. `timeout=31536000`). A first `-pl <module>` build resolves the whole dependency tree; a short timeout looks like a hang. A command that "timed out" is usually the timeout being too small, not a real hang.
- **Skip project-wide quality gates for your scoped run** if they fail on an unrelated part (`-Dcheckstyle.skip -Dspotless.check.skip -Denforcer.skip -Dspotbugs.skip -Dpmd.skip`), but your OWN fix + test must still be clean and idiomatic (rule 10) — re-enable before the PR.
