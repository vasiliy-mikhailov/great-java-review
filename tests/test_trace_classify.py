"""L5 (+ the classifier half of H1) — _trace_shows_fail / _trace_shows_pass must be accurate
across Maven, Gradle and JUnitCore, and must NOT mistake a build/compile event for a test result.

L5(a): a Gradle test failure that prints `> Task :test FAILED` / `There were failing tests` but
       no surefire-style count line must still register as a FAIL (today only the count line is
       matched -> real Gradle reproductions are dropped to inconclusive).
L5(b): a cached `> Task :test UP-TO-DATE` (no test executed) must NOT register as a PASS.
H1 prereq: a COMPILE failure (BUILD FAILURE / Task :compileJava FAILED) is not a test failure;
       a "No tests to run" green build is not a pass. The flip relies on these being right.
"""
from _fakes import (PipelineTC, MAVEN_PASS, MAVEN_FAIL, MAVEN_NO_TESTS, MAVEN_COMPILE_FAIL,
                    GRADLE_PASS, GRADLE_PASS_COUNTS, GRADLE_UP_TO_DATE, GRADLE_FAIL,
                    GRADLE_COMPILE_FAIL)
from current_version import suspicion as S


def _f(trace, rc=1):
    return {"trace": trace, "rc": rc}


class TestShowsFail(PipelineTC):
    def test_maven_failure(self):
        self.assertTrue(S._trace_shows_fail(_f(MAVEN_FAIL)))

    def test_gradle_failure_without_count_line(self):
        self.assertTrue(S._trace_shows_fail(_f(GRADLE_FAIL)),
                        "Gradle '> Task :test FAILED' not recognised as a failure (L5a)")

    def test_maven_compile_failure_is_not_a_test_failure(self):
        self.assertFalse(S._trace_shows_fail(_f(MAVEN_COMPILE_FAIL)),
                         "a Maven compile failure was mistaken for a test failure (H1)")

    def test_gradle_compile_failure_is_not_a_test_failure(self):
        self.assertFalse(S._trace_shows_fail(_f(GRADLE_COMPILE_FAIL)),
                         "a Gradle compile failure was mistaken for a test failure (H1)")

    def test_no_tests_is_not_a_failure(self):
        self.assertFalse(S._trace_shows_fail(_f(MAVEN_NO_TESTS, rc=0)))

    def test_clean_pass_is_not_a_failure(self):
        self.assertFalse(S._trace_shows_fail(_f(MAVEN_PASS, rc=0)))

    def test_no_failures_phrase_is_not_a_failure(self):
        # "There were no failures." (and non-test plugin failures) must not match the gradle fail clause.
        self.assertFalse(S._trace_shows_fail(_f("There were no failures.\nBUILD SUCCESS", rc=0)),
                         "'There were no failures.' was classified as a test failure (L5)")

    def test_plugin_failure_is_not_a_test_failure(self):
        self.assertFalse(S._trace_shows_fail(_f("There were 2 bug failures found.\nBUILD FAILURE", rc=1)),
                         "a spotbugs/enforcer plugin failure was classified as a test failure (L5)")

    def test_gradle_failing_tests_phrase_still_fails(self):
        self.assertTrue(S._trace_shows_fail(_f("There were failing tests. See the report.\nBUILD FAILED")))


class TestShowsPass(PipelineTC):
    def test_maven_pass(self):
        self.assertTrue(S._trace_shows_pass(_f(MAVEN_PASS, rc=0)))

    def test_gradle_pass_executed_task(self):
        self.assertTrue(S._trace_shows_pass(_f(GRADLE_PASS, rc=0)),
                        "an executed Gradle test task with BUILD SUCCESSFUL should be a pass")

    def test_gradle_pass_with_counts(self):
        self.assertTrue(S._trace_shows_pass(_f(GRADLE_PASS_COUNTS, rc=0)))

    def test_gradle_up_to_date_is_not_a_pass(self):
        self.assertFalse(S._trace_shows_pass(_f(GRADLE_UP_TO_DATE, rc=0)),
                         "a cached UP-TO-DATE Gradle build (no test ran) was counted as a pass (L5b)")

    def test_no_tests_is_not_a_pass(self):
        self.assertFalse(S._trace_shows_pass(_f(MAVEN_NO_TESTS, rc=0)),
                         "'No tests to run' must not count as a passing test run")

    def test_failure_is_not_a_pass(self):
        self.assertFalse(S._trace_shows_pass(_f(MAVEN_FAIL, rc=1)))
