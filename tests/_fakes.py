"""Shared test scaffolding for the pipeline regression suite.

These are UNIT/integration tests for the reward genome (src/current_version/suspicion.py +
sandbox.py) — the code that actually trains the model, so each confirmed bug from the code
review is pinned here fail-before / pass-after (TDD).

Run them all:
    PYTHONPATH=src:tests venv-oh/bin/python -m unittest discover -s tests -p 'test_*.py' -v

The pipeline keeps process-wide mutable globals (_RUNS / _STORE / _VERDICT / _FIX) and a module
handle to the real Docker sandbox (_sandbox). PipelineTC resets the globals around every test and
restores the sandbox handle + os.environ, so tests never bleed into each other and never touch
Docker (a FakeSandbox stands in where the orchestration needs one).
"""
from __future__ import annotations
import os
import shutil
import tempfile
import unittest

from current_version import suspicion as S
from current_version import sandbox as SB


class FakeSandbox:
    """In-memory stand-in for current_version.sandbox, scriptable per version.

    scripts maps "new"/"old" -> either a list of (rc, output) consumed in order (last value
    sticks), or a callable(command) -> (rc, output). workdir() returns real temp dirs so the
    suspicion module's _write_scaffold/_read_worktree_file work against actual files; reset_clean()
    genuinely empties them (so a fix that re-materializes the test after a reset is observable).
    """

    def __init__(self, scripts=None, tracked=None):
        self.calls = []
        self._scripts = scripts or {}
        self._idx = {"new": 0, "old": 0}
        self._new = tempfile.mkdtemp(prefix="fake_new_")
        self._old = tempfile.mkdtemp(prefix="fake_old_")
        # files git would restore on `git checkout` (e.g. the tracked pom.xml). reset_clean() wipes the
        # tree then puts these back, so a fix that re-applies a build edit after a reset is observable.
        self._tracked = dict(tracked or {})
        self._restore_tracked()

    def _restore_tracked(self):
        for rel, content in self._tracked.items():
            for base in (self._new, self._old):
                p = os.path.join(base, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as f:
                    f.write(content)

    def workdir(self, version="new"):
        return self._old if version == "old" else self._new

    def reset_clean(self):
        self.calls.append("reset_clean")
        for d in (self._new, self._old):
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)
        self._restore_tracked()

    def exec_(self, command, timeout_s=None, version="new"):
        self.calls.append(("exec_", version, command))
        sc = self._scripts.get(version)
        if callable(sc):
            return sc(command)
        if isinstance(sc, list) and sc:
            i = self._idx[version]
            self._idx[version] = min(i + 1, len(sc) - 1)
            return sc[i]
        return (0, "")

    def dirty_files(self, version="new", prefix=""):
        return {}

    def diff_numstat(self, version="new"):
        return []

    def set_no_new_files(self, on):  # noqa: ARG002
        pass

    def cleanup(self):
        shutil.rmtree(self._new, ignore_errors=True)
        shutil.rmtree(self._old, ignore_errors=True)


class PipelineTC(unittest.TestCase):
    """Base case: snapshot/restore process globals + env + the sandbox handle around each test."""

    def setUp(self):
        S._reset_store()
        S._reset_verdict()
        S._reset_fix()
        self._orig_sandbox = S._sandbox
        self._orig_env = dict(os.environ)
        # sandbox.py module-level mutable state we may poke
        self._orig_session = dict(SB._SESSION)
        self._orig_sb_run = SB._run

    def tearDown(self):
        S._sandbox = self._orig_sandbox
        SB._run = self._orig_sb_run
        SB._SESSION.clear()
        SB._SESSION.update(self._orig_session)
        os.environ.clear()
        os.environ.update(self._orig_env)
        S._reset_store()
        S._reset_verdict()
        S._reset_fix()

    def use_fake_sandbox(self, scripts=None, tracked=None):
        fake = FakeSandbox(scripts, tracked)
        S._sandbox = fake
        self.addCleanup(fake.cleanup)
        return fake

    def patch_attr(self, module, name, value):
        """Temporarily rebind module.name, auto-restored after the test (addCleanup)."""
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)
        return value


# --- realistic build/test output fixtures (so trace classifiers see the real shapes) ----------
MAVEN_PASS = (
    "Running com.example.FooBugTest\n"
    "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0\n"
    "BUILD SUCCESS\n"
)
MAVEN_FAIL = (
    "Running com.example.FooBugTest\n"
    "Tests run: 1, Failures: 1, Errors: 0, Skipped: 0\n"
    "<<< FAILURE!\n"
    "BUILD FAILURE\n"
)
MAVEN_NO_TESTS = (
    "No tests to run.\n"
    "BUILD SUCCESS\n"
)
MAVEN_COMPILE_FAIL = (
    "[ERROR] COMPILATION ERROR :\n"
    "[ERROR] /src/new/Foo.java:[12,5] cannot find symbol\n"
    "BUILD FAILURE\n"
)
GRADLE_PASS = (
    "> Task :compileJava\n"
    "> Task :test\n"
    "BUILD SUCCESSFUL in 4s\n"
)
GRADLE_PASS_COUNTS = (
    "> Task :test\n"
    "3 tests completed\n"
    "BUILD SUCCESSFUL in 4s\n"
)
GRADLE_UP_TO_DATE = (
    "> Task :compileJava UP-TO-DATE\n"
    "> Task :test UP-TO-DATE\n"
    "BUILD SUCCESSFUL in 1s\n"
)
GRADLE_FAIL = (
    "> Task :test FAILED\n"
    "There were failing tests. See the report at: file:///x\n"
    "BUILD FAILED in 5s\n"
)
GRADLE_COMPILE_FAIL = (
    "> Task :compileJava FAILED\n"
    "error: cannot find symbol\n"
    "BUILD FAILED in 2s\n"
)
