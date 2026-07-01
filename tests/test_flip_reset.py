"""C2 + H1 — the executable flip gate must be hermetic and judged on real test results.

C2 (root cause A): there is no reset_clean() between reproduce() returning and the flip, so the
   flip's /src/new run executes against the reproducer's CONTAMINATED tree (it can edit_file
   production code to fabricate a regression). The flip must reset both trees to pristine PR code
   and re-materialize the test before running, so a production edit can't survive into the gate.
H1: _flip_check decides new_fails/old_passes from RAW EXIT CODES, so a compile failure or a
   no-tests-matched run is misread as the bug manifesting / the test passing. It must use
   _trace_shows_fail / _trace_shows_pass.
"""
import os

from _fakes import (PipelineTC, MAVEN_PASS, MAVEN_FAIL, MAVEN_NO_TESTS, MAVEN_COMPILE_FAIL)
from current_version import suspicion as S

TEST_PATH = "mod/src/test/java/x/FooBugTest.java"


def _suspicion():
    return S.Suspicion(id=0, observation="o", suspected_bug="b", location="l", confidence=0.9)


def _verdict():
    return {"verdict": "confirmed", "repro_kind": "regression_test",
            "test_cmd": "mvn test -Dtest=FooBugTest -pl mod",
            "test_path": TEST_PATH, "test_src": "class FooBugTest {}", "test_files": {}}


class TestFlipReset(PipelineTC):
    def test_flip_resets_before_running(self):
        """A genuine regression (red on new, green on old) is still approved, AND the gate first
        resets the trees to pristine + re-materializes the test (defeats production-edit fabrication)."""
        fake = self.use_fake_sandbox(scripts={"new": [(1, MAVEN_FAIL)], "old": [(0, MAVEN_PASS)]})
        ok, how = S._validate_bug(_suspicion(), _verdict())
        self.assertIn("reset_clean", fake.calls,
                      "the flip ran without resetting the contaminated tree first (C2)")
        self.assertTrue(ok)
        self.assertEqual(how, "flip")
        self.assertTrue(os.path.isfile(os.path.join(fake.workdir("new"), TEST_PATH)),
                        "the test was not re-materialized into /src/new after the reset (C2)")

    def test_reset_happens_before_first_new_exec(self):
        fake = self.use_fake_sandbox(scripts={"new": [(1, MAVEN_FAIL)], "old": [(0, MAVEN_PASS)]})
        S._validate_bug(_suspicion(), _verdict())
        first_exec = next((i for i, c in enumerate(fake.calls)
                           if isinstance(c, tuple) and c[0] == "exec_"), None)
        self.assertIsNotNone(first_exec)
        self.assertIn("reset_clean", fake.calls[:first_exec],
                      "reset_clean must run before the first /src/new execution")


class TestFlipReappliesBuildEdit(PipelineTC):
    """C2 regression guard: reset_clean wipes the reproducer's test-scope dep (mockito-core added to
    pom.xml); the flip must re-apply it to BOTH trees, or a mock-based test fails to COMPILE and a genuine
    bug is wrongly rejected — the dominant repro style here."""

    def test_build_edit_reapplied_to_new_tree(self):
        # pom.xml is a TRACKED file (survives reset_clean as pristine), then the build edit overwrites it.
        fake = self.use_fake_sandbox(scripts={"new": [(1, MAVEN_FAIL)], "old": [(0, MAVEN_PASS)]},
                                     tracked={"mod/pom.xml": "<project>PRISTINE</project>"})
        v = _verdict()
        v["build_edit_path"] = "mod/pom.xml"
        v["build_edit_src"] = "<project>WITH-MOCKITO</project>"
        S._validate_bug(_suspicion(), v)
        for ver in ("new", "old"):
            pom = os.path.join(fake.workdir(ver), "mod/pom.xml")
            self.assertEqual(open(pom).read(), "<project>WITH-MOCKITO</project>",
                             f"build_edit (mockito dep) not re-applied to /src/{ver} after reset (C2)")


class TestFlipJudgesTraces(PipelineTC):
    def test_compile_failure_on_new_is_not_a_flip(self):
        """new fails to COMPILE (exit!=0 but no test failed) and old matches no tests (exit 0):
        raw exit codes read this as a perfect flip; it must not be approved as one."""
        fake = self.use_fake_sandbox(scripts={"new": [(1, MAVEN_COMPILE_FAIL)],
                                              "old": [(0, MAVEN_NO_TESTS)]})
        ok, how = S._validate_bug(_suspicion(), _verdict())
        self.assertNotEqual(how, "flip",
                            "a compile failure + no-tests run was accepted as a real regression flip (H1)")
        self.assertFalse(ok)

    def test_genuine_flip_still_approved(self):
        fake = self.use_fake_sandbox(scripts={"new": [(1, MAVEN_FAIL)], "old": [(0, MAVEN_PASS)]})
        ok, how = S._validate_bug(_suspicion(), _verdict())
        self.assertTrue(ok)
        self.assertEqual(how, "flip")
