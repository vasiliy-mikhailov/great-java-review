"""GEPA over the AGENT POLICY (Attempt 2 / P11).

Difference from gepa_run.py (static prompt evolution):
  - genome   = the agent SYS *policy* (when to repomap / read / grep / STOP),
               not the review-writing instruction.
  - rollout  = the whole ReAct TRAJECTORY (repomap -> reads -> greps -> review),
               run against the repo checked out at the PR base commit.
  - score    = final review vs the human review (outcome only).
  - critic   = metric feedback  PLUS  trajectory signals (budget used, whether it
               self-terminated, how many tool calls were REPEATED) — so reflection
               can fix *behaviour*: "stop earlier on high-base PRs; don't re-grep
               the same pattern; open the test before reviewing."

This is the mechanism that should push past the whole-MR plateau toward the
~0.485 human ceiling, by optimising HOW the agent investigates.

Usage:
  python src/gepa_agent.py --logins franz1981,radcortez   # materialize + optimize
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import gepa  # noqa: E402
from gepa import EvaluationBatch, GEPAAdapter  # noqa: E402

import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_review import SYS as AGENT_SEED, agent_review, MAX_STEPS  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from gepa_run import reflection_lm, GCFG, RESULTS, PROMPTS  # noqa: E402

POLICY_KEY = "agent_policy"


# ---- trajectory analysis: turn a raw trace into critic-readable signals -------
def traj_stats(trace, max_steps=MAX_STEPS):
    """trace = [(\"tool arg\", obs_snippet), ...] as returned by agent_review."""
    steps = [t for t, _ in trace]
    self_term = bool(steps) and steps[-1].startswith(("review", "no-action"))
    calls = [s for s in steps if not s.startswith(("review", "no-action"))]
    n = len(calls)
    repeats = sum(c - 1 for c in Counter(calls).values() if c > 1)  # wasted re-calls
    tool_mix = Counter(s.split()[0] for s in calls)
    return {"n_tool_calls": n, "self_terminated": self_term,
            "budget_exhausted": (not self_term) and n >= max_steps,
            "repeated_calls": repeats, "tool_mix": dict(tool_mix),
            "sequence": [s.split()[0] for s in calls]}


def traj_feedback(st):
    bits = [f"trajectory: {st['n_tool_calls']} tool calls "
            f"({'self-terminated via ACTION: review' if st['self_terminated'] else 'BUDGET EXHAUSTED without stopping — too much exploration'})."]
    if st["repeated_calls"]:
        bits.append(f"{st['repeated_calls']} calls were REPEATS of an earlier "
                    "identical call (wasted budget — instruct the agent not to "
                    "repeat a grep/read it already ran).")
    mix = ", ".join(f"{k}:{v}" for k, v in st["tool_mix"].items())
    bits.append(f"tool mix [{mix}].")
    return " ".join(bits)


# ---- dataset: attach a local repo @ base commit to each instance -------------
def materialize(logins, per_login=8):
    """Build agent instances: each needs a repo checked out at the PR base sha.
    Single-worker git (ban-safe). Skips PRs whose repo won't clone/checkout."""
    inst = ds.build_instances()
    out = []
    for login in logins:
        got = 0
        for x in inst.get(login, []):
            if got >= per_login:
                break
            sha = base_sha(x["repo"], x["pr"])
            if not sha:
                continue
            d = ensure_repo(x["repo"], sha)
            if d is None:
                continue
            out.append({**x, "repo_dir": str(d)})
            got += 1
        print(f"  {login}: {got} materialized", flush=True)
    return out


class AgentPolicyAdapter(GEPAAdapter):
    def __init__(self, profile="qwen", max_steps=MAX_STEPS):
        self.profile = profile
        self.max_steps = max_steps

    def evaluate(self, batch, candidate, capture_traces=False):
        policy = candidate[POLICY_KEY]
        outputs, scores, trajs = [], [], []
        for k, inst in enumerate(batch):         # serial: each rollout is many LLM calls
            try:
                review, trace = agent_review(
                    inst["repo_dir"], inst["input"], self.profile,
                    self.max_steps, policy=policy)
                st = traj_stats(trace, self.max_steps)
                score, fb = mt.score_with_feedback(
                    inst["input"], review, inst["reference_review"], self.profile)
            except Exception as e:  # noqa: BLE001
                review, score, fb, st, trace = "", 0.0, f"rollout-error:{e}", \
                    {"n_tool_calls": 0, "self_terminated": False, "budget_exhausted":
                     False, "repeated_calls": 0, "tool_mix": {}, "sequence": []}, []
            print(f"    rollout {k + 1}/{len(batch)} {inst.get('reviewer','?')} "
                  f"{inst.get('repo','').split('/')[-1]}#{inst.get('pr','')}  "
                  f"score={score:.3f}  {st['n_tool_calls']}t "
                  f"{'stop' if st['self_terminated'] else 'BUDGET'} "
                  f"rep={st['repeated_calls']}", flush=True)
            outputs.append(review)
            scores.append(score)
            trajs.append({"input": inst["input"], "reference": inst["reference_review"],
                          "generated": review, "score": score, "metric_fb": fb,
                          "stats": st, "trace": trace,
                          "reviewer": inst.get("reviewer"),
                          "repo": inst.get("repo"), "pr": inst.get("pr")})
        return EvaluationBatch(outputs=outputs, scores=scores,
                               trajectories=(trajs if capture_traces else None))

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        recs = []
        for tr in (eval_batch.trajectories or []):
            recs.append({
                "Inputs": tr["input"][:2200],
                "Target review to PREDICT (HIDDEN at inference)": tr["reference"][:1600],
                "Generated review": tr["generated"][:1600],
                # PURE MIMICRY feedback — NO efficiency/stop-early nudge (v1 over-fit
                # "be terse" because that nudge isn't in the reward; let output length
                # follow the TARGET reviewer's depth, not a hand-injected prior).
                "Feedback": (f"score={tr['score']:.2f}. {tr['metric_fb']} "
                             "Improve the POLICY so the review MATCHES THIS target "
                             "reviewer's specific concerns, DEPTH, and voice: if the "
                             "target raised many points, achieve comparable COVERAGE; "
                             "if the target was terse, be terse. Investigate the repo "
                             "as much as needed to find the issues the target found — "
                             "do not under-investigate. Keep one '%d' placeholder."),
            })
        return {comp: recs for comp in components_to_update}


def run(logins, profile="qwen", per_login=8, max_calls=None):
    data = materialize(logins, per_login)
    if len(data) < 6:
        print(f"only {len(data)} instances materialized; need >=6"); return None
    # deterministic train/val split (last 1/3 held out)
    cut = max(4, int(len(data) * 2 / 3))
    tr, va = data[:cut], data[cut:]
    print(f"[gepa-agent] train={len(tr)} val={len(va)}", flush=True)
    adapter = AgentPolicyAdapter(profile)
    tag = f"{profile}_agent_" + "_".join(logins)[:40]
    run_dir = str(RESULTS / "runs" / tag)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    res = gepa.optimize(
        seed_candidate={POLICY_KEY: AGENT_SEED},
        trainset=tr, valset=va, adapter=adapter,
        reflection_lm=reflection_lm(profile),
        reflection_minibatch_size=GCFG.get("reflection_minibatch", 2),
        max_metric_calls=max_calls or GCFG["max_metric_calls"],
        candidate_selection_strategy="pareto",
        seed=GCFG.get("seed", 7), run_dir=run_dir,
        display_progress_bar=False, track_best_outputs=True,
        raise_on_exception=False,
    )
    best = res.best_candidate[POLICY_KEY]
    out = PROMPTS / f"agent_policy.{profile}.txt"
    out.write_text(best)
    (RESULTS / f"gepa_agent_{profile}.json").write_text(json.dumps(
        {"logins": logins, "val_score": getattr(res, "val_aggregate_scores", None),
         "best_policy_path": str(out)}, indent=2, default=str))
    print(f"[gepa-agent] best policy -> {out}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--logins", required=True, help="comma-separated reviewer logins")
    ap.add_argument("--profile", default="qwen")
    ap.add_argument("--per-login", type=int, default=8)
    ap.add_argument("--max-calls", type=int, default=None)
    a = ap.parse_args()
    run([l.strip() for l in a.logins.split(",") if l.strip()],
        a.profile, a.per_login, a.max_calls)
