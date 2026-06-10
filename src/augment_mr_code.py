"""Add the MIDDLE condition — MR + code (no tools) — to the captured PRs, so we can do
the 3-way: mr_only (diff_only) / mr_code (notools) / mr_code_tools (delegation).

  ./venv-oh/bin/python -u src/augment_mr_code.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import metric as mt  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from oh_delegate import mr_code_review  # noqa: E402


def main():
    for fn in ("results/qual_capture.json", "results/qual_capture2.json"):
        try:
            data = json.load(open(fn))
        except Exception:  # noqa: BLE001
            continue
        for r in data:
            if r.get("mr_code_notools"):
                continue
            d = ensure_repo(r["repo"], base_sha(r["repo"], r["pr"]))
            rv = mr_code_review(str(d), r["pr_input"])
            s, _ = mt.score_with_feedback(r["pr_input"], rv, r["human"])
            r["mr_code_notools"] = rv
            r["mr_code_notools_score"] = round(s, 4)
            print(f"  {r['repo'].split('/')[-1]}#{r['pr']}: mr_code(no-tools) "
                  f"len={len(rv)} score={s:.3f}", flush=True)
            json.dump(data, open(fn, "w"), indent=2)
        print(f"{fn} augmented", flush=True)


if __name__ == "__main__":
    main()
