"""L1 + L10 + L11 — contract-drift / cosmetic fixes that still matter.

L1: the solver is wired edit_file (no src/test guard), not the edit_code its own prompt promises,
    so it CAN edit the regression test that grades it. Wire edit_code (refuses src/test).
L10: pr_files prints `+? -?` for a renamed+edited file because numstat keys the rename as
    `src/{Old => New}.java` while name-status looks up the resolved new path.
L11: search's missing-path hint points the model at the retired `sandbox_exec` tool.
"""
from types import SimpleNamespace

from _fakes import PipelineTC
from current_version import suspicion as S


class TestSolverUsesEditCode(PipelineTC):
    def test_solver_tool_set_uses_edit_code(self):
        self.assertIn("edit_code", S._SOLVER_TOOLS)
        self.assertNotIn("edit_file", S._SOLVER_TOOLS,
                         "solver still wired edit_file -> it can edit the test that grades it (L1)")
        self.assertIn("run_java", S._SOLVER_TOOLS)
        self.assertIn("record_fix", S._SOLVER_TOOLS)

    def test_edit_code_refuses_src_test(self):
        fake = self.use_fake_sandbox()
        obs = S._EditCodeExecutor()(SimpleNamespace(
            path="mod/src/test/java/x/FooBugTest.java", find="a", replace="b", version="new"))
        self.assertIn("refused", obs.text.lower())

    def test_edit_code_refuses_src_test_via_traversal(self):
        """L7/L1: a path that normalizes INTO src/test (via ../) must be refused — otherwise the solver can
        weaken the regression test that grades it. Pin it: the file exists with the find-text, so on buggy
        code edit_code would actually rewrite it."""
        import os
        fake = self.use_fake_sandbox()
        root = fake.workdir("new")
        real = os.path.join(root, "mod/src/test/java/x/FooBugTest.java")
        os.makedirs(os.path.dirname(real), exist_ok=True)
        with open(real, "w") as f:
            f.write("assertEquals(expected, actual);")
        obs = S._EditCodeExecutor()(SimpleNamespace(
            path="mod/src/main/../test/java/x/FooBugTest.java",
            find="assertEquals(expected, actual)", replace="assertEquals(actual, actual)", version="new"))
        self.assertIn("refused", obs.text.lower(),
                      "edit_code let the solver edit the test via a ../ traversal (L7/L1)")
        self.assertEqual(open(real).read(), "assertEquals(expected, actual);",
                         "the regression test was modified through the traversal bypass")


class TestPrFilesRename(PipelineTC):
    def test_resolve_brace_rename(self):
        from current_version import pr_diff_tool as P
        self.assertEqual(P._resolve_rename("src/{Old => New}.java"), "src/New.java")

    def test_resolve_full_path_rename(self):
        from current_version import pr_diff_tool as P
        self.assertEqual(P._resolve_rename("a/old.java => b/new.java"), "b/new.java")

    def test_plain_path_unchanged(self):
        from current_version import pr_diff_tool as P
        self.assertEqual(P._resolve_rename("src/Normal.java"), "src/Normal.java")

    def test_numstat_counts_indexes_resolved_newpath(self):
        from current_version import pr_diff_tool as P
        counts = P._numstat_counts("3\t1\tsrc/{Old => New}.java\n0\t0\tnormal.java\n")
        self.assertEqual(counts.get("src/New.java"), ("3", "1"),
                         "a renamed+edited file's line counts weren't found under its new path (L10)")


class TestSearchHint(PipelineTC):
    def test_missing_path_hint_no_retired_tool(self):
        from current_version import search_tool as ST
        self.assertNotIn("sandbox_exec", ST._MISSING_PATH_HINT,
                         "search miss-hint still points at the retired sandbox_exec (L11)")
        self.assertIn("pr_file", ST._MISSING_PATH_HINT.lower())
