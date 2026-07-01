"""C1 + L7 — the structural no_cheat guarantees.

C1: run_java must run exactly ONE allowed program. exec_ pipes the whole string to `bash -s`, so ANY
    statement separator (newline, the `&` background op, `;`, `|`, a subshell `(...)`, command
    substitution `$(...)`/backticks, or exotic whitespace) lets a second statement (cp/mv/rm/sed/...)
    overwrite the class-under-test with a stub and "reproduce" against it — the whole no_cheat hole.
L7: create_test / edit_code validate on the RAW path but write at the NORMALIZED path, so
    `.../src/test/../../src/main/.../FooTest.java` passes the check yet lands outside src/test.
"""
from types import SimpleNamespace

from _fakes import PipelineTC
from current_version import suspicion as S


class TestRunJavaNoShell(PipelineTC):
    def _ran(self, fake):
        return [c for c in fake.calls if isinstance(c, tuple) and c[0] == "exec_"]

    def _assert_rejected(self, cmd):
        fake = self.use_fake_sandbox()
        S._RUNS.clear()
        S._RunJavaExecutor()(SimpleNamespace(command=cmd, version="new"))
        self.assertEqual(self._ran(fake), [], f"command reached the sandbox (no_cheat bypass): {cmd!r}")
        self.assertEqual(len(S._RUNS), 0, "a rejected command must not be recorded as a run")

    def _assert_runs(self, cmd):
        fake = self.use_fake_sandbox(scripts={"new": [(0, "BUILD SUCCESS")]})
        S._RunJavaExecutor()(SimpleNamespace(command=cmd, version="new"))
        self.assertTrue(self._ran(fake), f"a legitimate command was wrongly rejected: {cmd!r}")

    def test_newline_then_cp_is_rejected(self):
        self._assert_rejected("javac Foo.java\ncp /tmp/stub/Foo.java src/main/java/Foo.java")

    def test_newline_then_rm_is_rejected(self):
        self._assert_rejected("java -cp . X\nrm -rf src/test")

    def test_carriage_return_separator_is_rejected(self):
        self._assert_rejected("mvn test\rgradle test")

    def test_ampersand_background_chain_is_rejected(self):
        """`&` (background op) separates statements and was NOT blocked (only `&&`/`||` were) — it lets a
        second command overwrite/delete the class-under-test. Tokens like ` cp ` miss `&cp` (no space)."""
        for cmd in (
            "javac src/main/java/Foo.java &cp /tmp/stub/Foo.java src/main/java/Foo.java",
            "java -cp . X &rm src/main/java/Foo.java",
            "javac X.java & sed -i 's/return v/return null/' src/main/java/Svc.java",
            "javac X.java & truncate -s0 Svc.java",
            "javac X.java & install -m644 /tmp/stub.java Svc.java",
        ):
            self._assert_rejected(cmd)

    def test_subshell_and_substitution_rejected(self):
        for cmd in ("java -cp . $(cat /etc/passwd)", "javac `ls`.java X.java", "mvn test < /tmp/x",
                    "mvn test ; rm -rf x", "mvn test | tee log"):
            self._assert_rejected(cmd)

    def test_control_whitespace_separators_rejected(self):
        # NEL, LS, PS, vtab, form-feed: non-space whitespace bash may treat as a separator.
        for sep in ("\x85", "\u2028", "\u2029", "\x0b", "\x0c"):
            self._assert_rejected("mvn test" + sep + "cp a b")

    def test_legit_maven_command_runs(self):
        self._assert_runs("mvn test -Dtest=FooBugTest -pl modules/core")

    def test_legit_gradle_command_runs(self):
        self._assert_runs("gradle :mod:test --tests com.x.FooBugTest")

    def test_legit_javac_classpath_runs(self):
        self._assert_runs("javac -cp target/classes:lib/* src/test/java/x/FooBugTest.java")

    def test_legit_junit5_nested_selector_runs(self):
        """A JUnit5 @Nested selector needs a `$` (Outer$Nested). It must be allowed — `$(`/`${` stay
        blocked via the `(`/`{` rules, so command substitution is still impossible."""
        self._assert_runs("mvn test -Dtest='Outer$Nested' -pl modules/core")
        self._assert_runs("gradle :m:test --tests com.x.Outer$Nested")

    def test_param_expansion_still_rejected(self):
        self._assert_rejected("mvn ${HOME}/x test")  # ${ blocked via {

    def test_non_allowed_program_rejected(self):
        self._assert_rejected("cat /etc/passwd")


class TestIsTestPathNormalization(PipelineTC):
    def test_traversal_escaping_src_test_is_rejected(self):
        self.assertFalse(
            S._is_test_path("mod/src/test/../../src/main/java/x/FooTest.java"),
            "traversal path escaping src/test was accepted as a test path (L7)")

    def test_plain_test_path_still_accepted(self):
        self.assertTrue(S._is_test_path("mod/src/test/java/x/FooBugTest.java"))
        self.assertTrue(S._is_test_path("a/src/test/java/x/FooIT.java"))
        self.assertTrue(S._is_test_path("a/src/test/java/x/FooTests.java"))

    def test_main_path_still_rejected(self):
        self.assertFalse(S._is_test_path("mod/src/main/java/x/FooTest.java"))
        self.assertFalse(S._is_test_path("mod/src/test/java/x/Helper.java"))
