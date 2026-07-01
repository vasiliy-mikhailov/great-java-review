"""C3 + M5 + reproducer confirm gate — proof traces must be bound to the BUG'S OWN test.

Root cause B: _last_pass_trace/_last_fail_trace scan ALL of _RUNS with no link to the bug's
test command, so:
  C3 (solver): a no-op "fix" that runs any already-green unrelated test captures that green run
      as proof -> passes -> reward 1.0 for zero work.
  reproducer:  an unrelated failing run becomes bug_trace, so the confirm gate passes on proof
      from a different test.
  M5: when no real green run is captured, fix_rerun falls back to the model's PROSE `rerun` arg,
      so paraphrased/fabricated "after the fix" text ships in the PR.
"""
from types import SimpleNamespace

from _fakes import PipelineTC, MAVEN_PASS, MAVEN_FAIL
from current_version import suspicion as S

# Runs of a DIFFERENT test — neither the command nor the trace names FooBugTest, so they must not
# bind as proof for it.
OTHER_PASS = ("$ mvn test -Dtest=OtherTest\nRunning com.example.OtherTest\n"
              "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0\nBUILD SUCCESS\n")
OTHER_FAIL = ("$ mvn test -Dtest=OtherTest\nRunning com.example.OtherTest\n"
              "Tests run: 1, Failures: 1, Errors: 0, Skipped: 0\n<<< FAILURE!\nBUILD FAILURE\n")


def _bug(**kw):
    d = dict(id=0, suspicion_id=0, observation="o", suspected_bug="b", location="l",
             repro_kind="regression_test", evidence="e", reproduction="r",
             test_path="mod/src/test/java/x/FooBugTest.java", test_src="class FooBugTest {}",
             test_cmd="mvn test -Dtest=FooBugTest -pl mod")
    d.update(kw)
    return S.Bug(**d)


class TestSolverTraceBinding(PipelineTC):
    def test_unrelated_green_run_does_not_count_as_fix_proof(self):
        """A green run of some OTHER test must not satisfy the solver's pass gate for THIS bug."""
        S._RUNS[:] = [{"cmd": "mvn test -Dtest=OtherTest -pl mod", "version": "new",
                       "rc": 0, "trace": OTHER_PASS}]
        bug = _bug()
        fix = {"fixed": True, "fix_diff": "x", "lines_changed": 1, "test_changed": False,
               "fix_trace": S._last_pass_trace(), "rerun": ""}
        sol = S._add_solution(bug, fix)
        self.assertEqual(sol.reward, 0.0,
                         "an unrelated green run was accepted as proof of the fix (C3)")

    def test_matching_green_run_does_count(self):
        """Regression guard: a green run of the bug's OWN test is valid proof."""
        S._RUNS[:] = [{"cmd": "mvn test -Dtest=FooBugTest -pl mod", "version": "new",
                       "rc": 0, "trace": "$ mvn test -Dtest=FooBugTest\n" + MAVEN_PASS}]
        bug = _bug()
        fix = {"fixed": True, "fix_diff": "x", "lines_changed": 1, "test_changed": False,
               "fix_trace": S._last_pass_trace(), "rerun": ""}
        sol = S._add_solution(bug, fix)
        self.assertGreater(sol.reward, 0.0, "a matching green run should yield a positive reward")


class TestSelectorCollision(PipelineTC):
    """A pathological-but-legal class name must not turn the selector into an everything-matching
    substring (e.g. `Test` ⊂ 'Tests run:', `C` ⊂ 'BUILD SUCCESSFUL')."""

    def test_short_maven_class_name_does_not_bind_unrelated_run(self):
        S._RUNS[:] = [{"cmd": "mvn test -Dtest=OtherTest -pl mod", "version": "new", "rc": 0,
                       "trace": "Running com.example.OtherTest\nTests run: 1, Failures: 0, Errors: 0\nBUILD SUCCESS"}]
        bug = _bug(test_cmd="mvn test -Dtest=Test -pl mod",
                   test_path="mod/src/test/java/x/Test.java", test_src="class Test {}")
        fix = {"fixed": True, "fix_diff": "x", "lines_changed": 1, "test_changed": False, "rerun": ""}
        self.assertEqual(S._add_solution(bug, fix).reward, 0.0,
                         "selector 'Test' collided with 'Tests run:' and bound an unrelated run (C3)")

    def test_single_letter_gradle_class_does_not_bind(self):
        S._RUNS[:] = [{"cmd": "gradle :mod:test --tests Other", "version": "new", "rc": 0,
                       "trace": "> Task :test\nBUILD SUCCESSFUL in 3s"}]
        bug = _bug(test_cmd="gradle :mod:test --tests C",
                   test_path="mod/src/test/java/x/C.java", test_src="class C {}")
        fix = {"fixed": True, "fix_diff": "x", "lines_changed": 1, "test_changed": False, "rerun": ""}
        self.assertEqual(S._add_solution(bug, fix).reward, 0.0,
                         "selector 'C' collided with 'BUILD SUCCESSFUL' and bound an unrelated run (C3)")

    def test_nested_class_selector_extracts_and_binds(self):
        sel = S._selector("mvn test -Dtest='Outer$Nested' -pl m")
        self.assertEqual(sel, "Outer$Nested", "quoted JUnit5 nested selector not extracted cleanly")
        run = {"cmd": "mvn test -Dtest='Outer$Nested' -pl m",
               "trace": "Running x.Outer$Nested\nTests run: 1, Failures: 0, Errors: 0\nBUILD SUCCESS"}
        self.assertTrue(S._run_matches(run, sel), "a nested-class test's own run must bind")

    def test_real_own_run_still_binds_for_short_name(self):
        S._RUNS[:] = [{"cmd": "mvn test -Dtest=Test -pl mod", "version": "new", "rc": 0,
                       "trace": "Running com.example.Test\nTests run: 1, Failures: 0, Errors: 0\nBUILD SUCCESS"}]
        bug = _bug(test_cmd="mvn test -Dtest=Test -pl mod",
                   test_path="mod/src/test/java/x/Test.java", test_src="class Test {}")
        fix = {"fixed": True, "fix_diff": "x", "lines_changed": 1, "test_changed": False, "rerun": ""}
        self.assertGreater(S._add_solution(bug, fix).reward, 0.0,
                           "a class's OWN run must still bind even with a short name")


class TestFixRerunNoProseFallback(PipelineTC):
    def test_fix_rerun_is_never_model_prose(self):
        """M5 — with no captured green run, fix_rerun must be empty, NOT the model's free text."""
        S._RUNS[:] = []  # no runs captured at all
        bug = _bug()
        fix = {"fixed": True, "fix_diff": "x", "lines_changed": 1, "test_changed": False,
               "fix_trace": "", "rerun": "trust me, all tests are green now"}
        sol = S._add_solution(bug, fix)
        self.assertNotIn("trust me", sol.fix_rerun,
                         "model prose leaked into the PR's after-fix proof (M5)")
        self.assertEqual(sol.reward, 0.0, "no captured green run must score 0")


class TestReproducerConfirmGateBinding(PipelineTC):
    def _record(self, fake, test_cmd):
        S._sandbox = fake
        action = SimpleNamespace(
            verdict="confirmed", repro_kind="regression_test",
            test_path="mod/src/test/java/x/FooBugTest.java", test_src="class FooBugTest {}",
            test_cmd=test_cmd, build_edit_path="", build_edit_src="",
            reproduction="ran it", evidence="FooBugTest fails")
        S._RecordVerdictExecutor()(action)
        return S._VERDICT.get("verdict")

    def test_confirm_rejected_when_only_unrelated_failing_run(self):
        """A failing run of a DIFFERENT test must not satisfy the confirm gate for this suspicion."""
        fake = self.use_fake_sandbox()
        S._RUNS[:] = [{"cmd": "mvn test -Dtest=OtherTest -pl mod", "version": "new",
                       "rc": 1, "trace": OTHER_FAIL}]
        verdict = self._record(fake, "mvn test -Dtest=FooBugTest -pl mod")
        self.assertEqual(verdict, "inconclusive",
                         "confirm accepted proof from an unrelated failing run (root cause B)")

    def test_confirm_accepted_with_matching_failing_run(self):
        """Regression guard: a failing run of the bug's own test confirms."""
        fake = self.use_fake_sandbox()
        S._RUNS[:] = [{"cmd": "mvn test -Dtest=FooBugTest -pl mod", "version": "new",
                       "rc": 1, "trace": "$ mvn test -Dtest=FooBugTest\n" + MAVEN_FAIL}]
        verdict = self._record(fake, "mvn test -Dtest=FooBugTest -pl mod")
        self.assertEqual(verdict, "confirmed")
        self.assertTrue(S._VERDICT.get("bug_trace"), "bug_trace must be captured for a confirm")
