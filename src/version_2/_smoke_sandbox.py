"""Smoke: prove the sandbox mounts BOTH versions — /src/old (base) and /src/new (post-PR
worktree) — and that the new code is present only in /src/new. Usage (in-docker via run.sh):
  python -u src/current_version/_smoke_sandbox.py <repo> <pr> <new-symbol-added-by-the-PR>"""
import sys, os
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from current_version import sandbox

repo, pr = sys.argv[1], sys.argv[2]
sym = sys.argv[3] if len(sys.argv) > 3 else "class "
sandbox.start(repo, pr)
try:
    for ver in ("new", "old"):
        rc, out = sandbox.exec_(
            f"echo '== /src/{ver} =='; ls | head -3; echo; "
            f"echo 'java files:' $(find . -name '*.java' 2>/dev/null | wc -l); "
            f"echo 'has new symbol ({sym}):' $(rg -l '{sym}' . 2>/dev/null | wc -l) files; "
            f"echo 'javac:' $(javac -version 2>&1)", version=ver)
        print(f"[exit {rc}]\n{out}")
finally:
    sandbox.stop()
