"""Review-mimicry metric.

Scores how well a *generated* review reproduces a target reviewer's *real*
review on the same PR. Combines:

  * judge  (Qwen LLM-as-judge): same issues found + same style/tone/structure,
            0..1, plus a short natural-language critique used as GEPA feedback.
  * lexical (rapidfuzz + file/keyword overlap): cheap, deterministic anchor that
            keeps the judge honest and degrades gracefully if the judge errors.

Returns (score in [0,1], feedback_text).
"""
from __future__ import annotations

import json
import re

from rapidfuzz import fuzz

from llm_client import get_llm

JUDGE_SYS = (
    "You are evaluating whether a CANDIDATE Java code review reproduces a "
    "REFERENCE review written by a specific expert reviewer for the same pull "
    "request. Judge two things:\n"
    "1) COVERAGE: does the candidate raise the same substantive concerns / "
    "pain points as the reference (correctness, concurrency, API design, "
    "tests, edge cases, performance)? Missing or inventing major points is bad.\n"
    "2) STYLE: does the candidate match the reference reviewer's voice - "
    "tone, directness, level of detail, use of code suggestions, structure?\n"
    "Return STRICT JSON: {\"coverage\":0-10,\"style\":0-10,"
    "\"feedback\":\"<=60 words, concrete: what the candidate missed or "
    "over/under-did vs the reference\"}."
)


def _file_overlap(cand: str, ref: str) -> float:
    fre = re.compile(r"[\w/]+\.java")
    a = set(fre.findall(cand)); b = set(fre.findall(ref))
    if not b:
        return 0.0
    return len(a & b) / len(b)


def lexical_score(cand: str, ref: str) -> float:
    tsr = fuzz.token_set_ratio(cand, ref) / 100.0
    fo = _file_overlap(cand, ref)
    return 0.7 * tsr + 0.3 * fo


def _parse_json(text: str) -> dict | None:
    from llm_client import last_json     # the FINAL {...} after any reasoning prose
    cand = last_json(text)
    if not cand:
        return None
    try:
        return json.loads(cand)
    except Exception:  # noqa: BLE001
        return None


def judge(pr_input: str, candidate: str, reference: str,
          profile: str = "qwen") -> tuple[float, str]:
    llm = get_llm(profile)
    user = (
        f"PULL REQUEST (truncated):\n{pr_input[:3500]}\n\n"
        f"REFERENCE REVIEW (expert):\n{reference[:2500]}\n\n"
        f"CANDIDATE REVIEW (to grade):\n{candidate[:2500]}\n\n"
        "Return the JSON now."
    )
    try:
        raw = llm.complete(JUDGE_SYS, user, temperature=0.0)  # full reasoning, no cap
        d = _parse_json(raw)
        if d:
            cov = float(d.get("coverage", 0)) / 10.0
            sty = float(d.get("style", 0)) / 10.0
            fb = str(d.get("feedback", ""))[:400]
            score = 0.65 * cov + 0.35 * sty
            return max(0.0, min(1.0, score)), fb
    except Exception as e:  # noqa: BLE001
        return -1.0, f"judge-error:{e}"
    return -1.0, "judge-unparseable"


def score_with_feedback(pr_input: str, candidate: str, reference: str,
                        profile: str = "qwen") -> tuple[float, str]:
    cand = (candidate or "").strip()
    if len(cand) < 15:
        return 0.0, "Candidate review is essentially empty."
    lex = lexical_score(cand, reference)
    js, fb = judge(pr_input, cand, reference, profile)
    if js < 0:  # judge failed -> fall back to lexical only
        return lex, f"(judge unavailable; lexical={lex:.2f}) {fb}"
    # judge dominates; lexical is a small anchor
    final = 0.85 * js + 0.15 * lex
    return final, fb
