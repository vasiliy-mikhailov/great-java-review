#!/usr/bin/env bash
# Progressive WIDE crawl: widen across hundreds of Java repos to grow the
# distinct-reviewer pool toward target_reviewers (~11k) so the Fibonacci sweep
# can reach k=10946. Single GitHub worker, resumable — safe to stop/restart.
#
#   ./run_wide.sh            # run in foreground (Ctrl-C to pause; resumes later)
#   nohup ./run_wide.sh &    # run in background for hours/days
#
# Monitor progress:
#   wc -l data/cache/comments_index.jsonl
#   ./venv/bin/python -c "import sys;sys.path.insert(0,'src');import crawl;print(len(crawl._distinct_reviewers()),'reviewers')"
set -uo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"      # for gh
export PYTHONUNBUFFERED=1                   # live logs
exec ./venv/bin/python src/crawl.py wide
