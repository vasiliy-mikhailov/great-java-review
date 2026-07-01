"""L3 — lines_changed must reflect the patch SIZE, not double-count in-place edits.

diff_numstat returns added+deleted per file, so an N-line in-place modification (git: +N -N)
counts as 2N -> the solver's 0.9^lines penalty is twice as steep as the prompt advertises
("5 lines ~ 0.59"). Use max(added, deleted): the number of lines a hunk touches.
"""
from _fakes import PipelineTC
from current_version import sandbox as SB


class _R:
    def __init__(self, out):
        self.returncode, self.stdout, self.stderr = 0, out, ""


class TestDiffNumstat(PipelineTC):
    def _numstat(self, out):
        SB._SESSION["base"] = "/x"
        SB._SESSION["worktree"] = "/y"
        self.patch_attr(SB, "_run", lambda *a, **k: _R(out))
        return dict(SB.diff_numstat("new"))

    def test_in_place_modification_not_double_counted(self):
        rows = self._numstat("5\t5\tsrc/main/java/Foo.java\n")
        self.assertEqual(rows["src/main/java/Foo.java"], 5,
                         "an in-place 5-line edit was counted as 10 (L3)")

    def test_pure_addition(self):
        rows = self._numstat("7\t0\tsrc/main/java/Bar.java\n")
        self.assertEqual(rows["src/main/java/Bar.java"], 7)

    def test_pure_deletion(self):
        rows = self._numstat("0\t4\tsrc/main/java/Baz.java\n")
        self.assertEqual(rows["src/main/java/Baz.java"], 4)

    def test_asymmetric_modification_uses_larger_side(self):
        rows = self._numstat("8\t3\tsrc/main/java/Q.java\n")
        self.assertEqual(rows["src/main/java/Q.java"], 8)

    def test_binary_dashes_count_zero(self):
        rows = self._numstat("-\t-\tsrc/main/resources/x.bin\n")
        self.assertEqual(rows["src/main/resources/x.bin"], 0)
