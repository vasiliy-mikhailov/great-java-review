"""M1 — exec_ must not impose a 120s wall-clock cap.

AGENTS.md P2/P8/P14 forbid wall-clock caps ("timeouts effectively to infinity"; "exit=124 = a
cap crept back"). exec_ hardcodes timeout_s=120, so cold-cache / reactor builds hit rc=124, which
poisons the flip and drops real bugs. The default must be large and overridable via env.
"""
import re

from _fakes import PipelineTC
from current_version import sandbox as SB


class _R:
    returncode, stdout, stderr = 0, "", ""


class TestExecTimeout(PipelineTC):
    def _capture(self):
        cap = {}

        def fake_run(remote, stdin="", timeout=240):
            cap["remote"] = remote
            cap["outer_timeout"] = timeout
            return _R()

        SB._SESSION["name"] = "review-x-0"
        self.patch_attr(SB, "_run", fake_run)
        return cap

    def _inner(self, cap):
        m = re.search(r"timeout -k 5 (\d+)", cap["remote"])
        self.assertIsNotNone(m, "no inner timeout found in the probe")
        return int(m.group(1))

    def test_default_timeout_is_large(self):
        cap = self._capture()
        SB.exec_("mvn test")
        self.assertGreaterEqual(self._inner(cap), 1800,
                                "exec_ still caps builds at the old 120s wall-clock (M1)")

    def test_env_override(self):
        cap = self._capture()
        import os
        os.environ["SANDBOX_EXEC_TIMEOUT_S"] = "777"
        SB.exec_("mvn test")
        self.assertEqual(self._inner(cap), 777)

    def test_explicit_arg_still_honoured(self):
        cap = self._capture()
        SB.exec_("mvn test", timeout_s=42)
        self.assertEqual(self._inner(cap), 42)
