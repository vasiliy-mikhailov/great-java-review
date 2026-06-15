"""Smoke: prove the per-session JDK sandbox sees the REAL repo (HOST_WORKDIR mount fixed) and
its toolchain works. Usage (in-docker via run.sh): python -u src/current_version/_smoke_sandbox.py <repo> <pr>"""
import sys, os
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from current_version import sandbox

repo, pr = sys.argv[1], sys.argv[2]
sandbox.start(repo, pr)
try:
    rc, out = sandbox.exec_(
        "echo '== /work (should be the repo, not empty) =='; ls /work | head; "
        "echo; echo '== .java files visible =='; find /work -name '*.java' 2>/dev/null | wc -l; "
        "echo; echo '== toolchain =='; javac -version 2>&1; mvn -v 2>&1 | head -1; "
        "echo; echo '== Maven mirror =='; sed -n 's|.*<url>\\(.*\\)</url>.*|\\1|p' /root/.m2/settings.xml")
    print(f"[exit {rc}]\n{out}")
finally:
    sandbox.stop()
