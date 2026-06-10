"""Grounded-judge the MIDDLE condition (mr_code, no tools) for the captured PRs, so we
have all three rungs scored on the same code-grounded point metric.

  ./venv-oh/bin/python -u src/judge_notools.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import point_judge_grounded as g  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402


def main():
    data = []
    for fn in ("results/qual_capture.json", "results/qual_capture2.json"):
        try:
            data += json.load(open(fn))
        except Exception:  # noqa: BLE001
            pass
    out = []
    for r in data:
        if not r.get("mr_code_notools"):
            continue
        tag = r["repo"].split("/")[-1] + "#" + str(r["pr"])
        d = ensure_repo(r["repo"], base_sha(r["repo"], r["pr"]))
        res = None
        for _ in range(3):
            res = g.grounded_judge(str(d), r["pr_input"], r["human"], r["mr_code_notools"])
            if res:
                break
            print(f"    {tag} parse-fail, retry…", flush=True)
        if not res:
            print(f"{tag:24} mr_code_notools  PARSE FAIL", flush=True); continue
        print(f"{tag:24} mr_code_notools net {res.get('net_score',0):>3} "
              f"good {res.get('n_good',0)} wrong {res.get('n_wrong',0)} "
              f"miss {res.get('n_missed',0)}", flush=True)
        out.append({"pr": tag, "cond": "mr_code_notools",
                    **{k: res.get(k) for k in ("net_score", "n_good", "n_wrong",
                                               "n_trivial", "n_missed")},
                    "detail": res.get("candidate")})
        json.dump(out, open("results/point_judge_notools.json", "w"), indent=2)


if __name__ == "__main__":
    main()
