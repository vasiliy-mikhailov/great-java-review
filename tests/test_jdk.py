"""M4 — Gradle JDK detection misses the canonical 1.x form.

`r"VERSION_(\\d{1,2})\\b"` cannot match Gradle's `JavaVersion.VERSION_1_8` (the \\b can't sit
between the two word chars `1` and `_`), so any Java<=10 Gradle repo silently falls to
DEFAULT_JDK=21 -> /src/new gets the wrong image -> false compile errors -> the flip can't run.
"""
import os
import tempfile

from _fakes import PipelineTC
from current_version import sandbox as SB


class TestDetectJdk(PipelineTC):
    def _repo(self, filename, content):
        d = tempfile.mkdtemp(prefix="jdk_repo_")
        self.addCleanup(__import__("shutil").rmtree, d, True)
        with open(os.path.join(d, filename), "w") as f:
            f.write(content)
        return d

    def test_gradle_version_1_8(self):
        d = self._repo("build.gradle", "sourceCompatibility = JavaVersion.VERSION_1_8\n")
        self.assertEqual(SB.detect_jdk(d), 11,
                         "Gradle VERSION_1_8 was not detected -> fell back to DEFAULT_JDK (M4)")

    def test_gradle_version_1_7(self):
        d = self._repo("build.gradle", "targetCompatibility = JavaVersion.VERSION_1_7\n")
        self.assertEqual(SB.detect_jdk(d), 11)

    def test_gradle_version_11(self):
        d = self._repo("build.gradle.kts", "sourceCompatibility = JavaVersion.VERSION_11\n")
        self.assertEqual(SB.detect_jdk(d), 11)

    def test_gradle_version_17(self):
        d = self._repo("build.gradle", "sourceCompatibility = JavaVersion.VERSION_17\n")
        self.assertEqual(SB.detect_jdk(d), 17)

    def test_maven_release_17_regression(self):
        d = self._repo("pom.xml", "<maven.compiler.release>17</maven.compiler.release>")
        self.assertEqual(SB.detect_jdk(d), 17)

    def test_undeclared_defaults(self):
        d = self._repo("README.md", "no java level here")
        self.assertEqual(SB.detect_jdk(d), SB.DEFAULT_JDK)
