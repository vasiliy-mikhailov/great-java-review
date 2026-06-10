"""Qwen rubric judge for curating HIGH-QUALITY reviews (P3 contract, stage 2).

Rates each heuristic-survivor review-unit 1-5 on whether it is concrete,
actionable TECHNICAL review (correctness / concurrency / API / security / tests /
design) vs. trivial chatter (LGTM / nit / style / process). Scores are cached in
data/cache/quality.jsonl keyed by repo#pr#review_id, so judging is incremental.

ACCEPTED tradeoff (operator-approved): Qwen is also the task model + metric judge,
so this selection can bias the corpus toward Qwen's taste. Disclosed in AGENTS.md.

Usage:
  python src/quality_judge.py reviewer <login>   # judge one reviewer's units
  python src/quality_judge.py all                # judge the whole survivor pool
  python src/quality_judge.py stats              # distribution of cached scores
"""
from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import wide_dataset as wds  # noqa: E402
from wide_dataset import quality_key, QUALITY_CACHE  # noqa: E402
from llm_client import get_llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())

RUBRIC = """You are curating training data: rate the QUALITY of one code-review unit.

Score 1-5 how substantive it is as TECHNICAL review feedback:
5 = identifies a concrete, actionable technical issue (correctness, concurrency/
    thread-safety, resource/memory, API/contract design, security, tests, edge
    cases) with specific reasoning tied to the code.
4 = a real technical point, somewhat specific/actionable.
3 = borderline: a minor but valid technical remark.
2 = mostly style/readability nit or vague suggestion.
1 = no technical substance: LGTM/+1, pure formatting, "rebase/merge/changelog",
    a bare question, or process/social chatter.

Think if you must, then end your reply with EXACTLY one line:
SCORE: <n>   (n = 1-5)"""


def _score_one(llm, inst) -> int:
    user = (f"CODE UNDER REVIEW:\n{inst['input'][:3500]}\n\n"
            f"REVIEWER'S REVIEW:\n{inst['reference_review'][:2500]}\n\n"
            "Score (1-5):")
    try:
        # no max_tokens cap -> full reasoning; client strips <think>, we parse the int
        out = llm.complete(RUBRIC, user, temperature=0.0)
    except Exception:  # noqa: BLE001
        return 0
    m = re.findall(r"SCORE:\s*([1-5])", out or "", re.I)   # the final SCORE: line
    if m:
        return int(m[-1])
    nums = re.findall(r"(?:^|\n)\s*([1-5])\s*$", out or "")  # fallback: trailing int
    return int(nums[-1]) if nums else 0


def judge(instances, profile="qwen"):
    """Judge uncached instances, append to cache, return {key: score}."""
    cache = wds.load_quality_cache()
    todo = [i for i in instances
            if quality_key(i["repo"], i["pr"], i["review_id"]) not in cache]
    print(f"[judge] {len(instances)} units, {len(todo)} uncached to score")
    if not todo:
        return cache
    llm = get_llm(profile)
    workers = CFG[profile].get("max_concurrency", 4) * 2   # short calls -> more parallelism
    QUALITY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    fout = QUALITY_CACHE.open("a")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        # as_completed -> write results out-of-order so one slow call never
        # head-of-line-blocks the rest.
        futs = {ex.submit(_score_one, llm, inst): inst for inst in todo}
        for fut in as_completed(futs):
            inst = futs[fut]
            try:
                score = fut.result()
            except Exception:  # noqa: BLE001
                score = 0
            key = quality_key(inst["repo"], inst["pr"], inst["review_id"])
            cache[key] = score
            fout.write(json.dumps({"key": key, "score": score,
                                   "reviewer": inst["reviewer"]}) + "\n")
            done += 1
            if done % 50 == 0:
                fout.flush(); print(f"[judge] {done}/{len(todo)} scored", flush=True)
    fout.flush(); fout.close()
    print(f"[judge] done: {done} new scores")
    return cache


def _survivors():
    # heuristic-floor survivors (no qwen gate) = the judging candidates
    return wds.build_wide_instances(min_ref_chars=CFG["fib_sweep"].get("min_ref_chars", 80),
                                    substantive_only=True, quality_gate=None)


def _deep_survivors():
    # DEEP pool: input is the WHOLE MR (title/body/full diff), the correct context
    import dataset as ds
    return ds.build_instances()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "deep":
        pool = _deep_survivors()
        allinst = [i for v in pool.values() for i in v]
        print(f"[judge] DEEP/full-MR pool: {len(pool)} reviewers, {len(allinst)} units")
        judge(allinst)
        return
    pool = _survivors()
    if cmd == "reviewer":
        login = sys.argv[2]
        judge(pool.get(login, []))
    elif cmd == "all":
        allinst = [i for v in pool.values() for i in v]
        judge(allinst)
    elif cmd == "stats":
        cache = wds.load_quality_cache()
        from collections import Counter
        c = Counter(cache.values())
        print("cached quality scores:", dict(sorted(c.items())))
        keep = sum(v >= CFG["selection"].get("quality_threshold", 4)
                   for v in cache.values())
        print(f"total judged={len(cache)}  kept(>= "
              f"{CFG['selection'].get('quality_threshold',4)})={keep}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
