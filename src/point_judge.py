"""Point-based review-quality judge — the 'better metric' (substance, not lexical echo).

Reference findings = the HUMAN review's findings (the gold). A candidate review is
scored by SUBSTANCE:
  +1  per GOOD finding it makes (correct + useful, whether or not the human said it)
  -1  per WRONG/FABRICATED finding (claims something false about the code → misleads)
   0  per trivial/vague point
  -1  per HUMAN finding the candidate MISSED
net_score = sum. Higher = better review independent of word overlap with the human.

Run as a smoke on the captured reviews:
  ./venv-oh/bin/python -u src/point_judge.py
"""
from __future__ import annotations
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from llm_client import get_llm  # noqa: E402

JUDGE_SYS = """You are a STRICT senior Java reviewer grading the QUALITY of a code
review by its FINDINGS (substance), not its wording. You are given a PR diff, the
HUMAN reviewer's review (the gold standard), and a CANDIDATE review to grade.

Do this:
1. Extract the CANDIDATE's distinct technical findings. For each, judge against the
   actual diff:
     - "good"   = correct AND useful (a real issue / valid suggestion)  -> +1
     - "wrong"  = FABRICATED or factually false about the code (misleads) -> -1
     - "trivial"= vague, restates the obvious, or no actionable content   ->  0
2. Extract the HUMAN's distinct findings. For each HUMAN finding the candidate did
   NOT make (missed), that is a miss -> -1.
3. net_score = (sum of candidate finding scores) + (sum of miss penalties).

Be skeptical of confident claims that aren't supported by the diff — those are
"wrong", not "good". Return ONLY this JSON (no prose, no markdown fence):
{"candidate_findings":[{"text":"...","verdict":"good|wrong|trivial","score":1}],
 "human_findings":["..."],
 "missed_human_findings":["..."],
 "n_good":0,"n_wrong":0,"n_trivial":0,"n_missed":0,"net_score":0}"""


def _extract_json(s: str):
    s = s.rsplit("</think>", 1)[-1]
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def judge(pr_input: str, human: str, candidate: str, profile: str = "qwen"):
    llm = get_llm(profile)
    user = (f"PR (description + diff):\n{pr_input[:16000]}\n\n"
            f"HUMAN REVIEW (gold):\n{human}\n\n"
            f"CANDIDATE REVIEW TO GRADE:\n{candidate}\n\n"
            "Grade the candidate per the rules. Return ONLY the JSON.")
    return _extract_json(llm.complete(JUDGE_SYS, user))


def smoke():
    data = []
    for fn in ("results/qual_capture.json", "results/qual_capture2.json"):
        try:
            data += json.load(open(fn))
        except Exception:  # noqa: BLE001
            pass
    print(f"{'PR':28} {'cond':9} {'net':>4} {'good':>4} {'wrong':>5} {'miss':>4} "
          f"{'(old metric)':>12}", flush=True)
    print("-" * 78, flush=True)
    for r in data:
        tag = r["repo"].split("/")[-1] + "#" + str(r["pr"])
        for cond in ("diff_only", "mr_code"):
            res = judge(r["pr_input"], r["human"], r[cond])
            if not res:
                print(f"{tag:28} {cond:9}  JUDGE PARSE FAIL", flush=True)
                continue
            print(f"{tag:28} {cond:9} {res.get('net_score',0):>4} "
                  f"{res.get('n_good',0):>4} {res.get('n_wrong',0):>5} "
                  f"{res.get('n_missed',0):>4} {r[cond + '_score']:>12.3f}", flush=True)


if __name__ == "__main__":
    smoke()
