"""GEPA over the OpenHands DELEGATION orchestrator prompt (Attempt 3).

Genome  = ORCH_SYS, the orchestrator system prompt (how it decomposes the PR and
          delegates to code-explorer subagents).
Rollout = oh_review_delegate against the repo @ base commit (orchestrator + subagents).
Score   = final review vs the human review (outcome only).
Critic  = pure-mimicry feedback (match the target reviewer's depth/voice) + light
          delegation stats (how many subtasks). NO efficiency/stop-early nudge —
          that over-fit "be terse" in the home-grown v1.

Runs under venv-oh (python>=3.12).

  ./venv-oh/bin/python src/gepa_oh.py --logins franz1981,radcortez,mkouba --per-login 6 --max-calls 40
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

sys.path.insert(0, os.path.dirname(__file__))
import gepa  # noqa: E402
from gepa import EvaluationBatch, GEPAAdapter  # noqa: E402

import metric as mt  # noqa: E402
from oh_delegate import oh_review_delegate, ORCH_SYS, MAX_ORCH_STEPS  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from gepa_run import reflection_lm, GCFG, CFG, RESULTS, PROMPTS  # noqa: E402

POLICY_KEY = "orch_policy"


GOLD_POOL = "data/cache/clean_both_technical.json"


def gated_materialize(logins, per_login=6, profile="qwen"):
    """Draw from the DUAL-JUDGED GOLD pool (Qwen>=4 AND Claude-technical, 2173
    reviews). Two independent model families agree these are substantive Java
    review — never the Qwen-only gate (which leaked non-Java + process chatter)."""
    import json as _json
    import dataset as ds
    from wide_dataset import quality_key
    gold = set(_json.load(open(GOLD_POOL)))
    inst = ds.build_instances()
    out, dropped = [], 0
    for lg in logins:
        kept = 0
        for x in inst.get(lg, []):
            if kept >= per_login:
                break
            if quality_key(x["repo"], x["pr"], x["review_id"]) not in gold:
                dropped += 1
                continue                            # not in dual-judged gold pool
            sha = base_sha(x["repo"], x["pr"])
            if not sha:
                continue
            d = ensure_repo(x["repo"], sha)
            if d is None:
                continue
            out.append({**x, "repo_dir": str(d)}); kept += 1
        print(f"  {lg}: {kept} gold instances", flush=True)
    print(f"  [gate] {len(out)} dual-judged gold instances (dropped {dropped} non-gold)", flush=True)
    return out


def traj_stats(trace):
    labels = [t for t, _ in trace]
    deleg = [s for s in labels if s.startswith("task")]
    self_term = any(s.startswith("finish") for s in labels)
    return {"orch_actions": len(labels), "delegations": len(deleg),
            "self_terminated": self_term}


def traj_feedback(st):
    return (f"orchestrator made {st['orch_actions']} actions, {st['delegations']} "
            f"subagent delegations"
            f"{'' if st['self_terminated'] else ' (did NOT finish cleanly)'}.")


class OrchAdapter(GEPAAdapter):
    def __init__(self, profile="qwen", max_steps=MAX_ORCH_STEPS):
        self.profile = profile
        self.max_steps = max_steps

    def evaluate(self, batch, candidate, capture_traces=False):
        policy = candidate[POLICY_KEY]
        outputs, scores, trajs = [], [], []
        for k, inst in enumerate(batch):
            try:
                review, trace = oh_review_delegate(
                    inst["repo_dir"], inst["input"], self.profile,
                    self.max_steps, policy=policy)
                st = traj_stats(trace)
                score, fb = mt.score_with_feedback(
                    inst["input"], review, inst["reference_review"], self.profile)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                review, score, fb = "", 0.0, f"rollout-error:{e}"
                st = {"orch_actions": 0, "delegations": 0, "self_terminated": False}
            print(f"    rollout {k + 1}/{len(batch)} {inst.get('reviewer','?')} "
                  f"{inst.get('repo','').split('/')[-1]}#{inst.get('pr','')}  "
                  f"score={score:.3f}  {st['delegations']} deleg", flush=True)
            outputs.append(review)
            scores.append(score)
            trajs.append({"input": inst["input"], "reference": inst["reference_review"],
                          "generated": review, "score": score, "metric_fb": fb,
                          "stats": st, "reviewer": inst.get("reviewer")})
        return EvaluationBatch(outputs=outputs, scores=scores,
                               trajectories=(trajs if capture_traces else None))

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        recs = []
        for tr in (eval_batch.trajectories or []):
            recs.append({
                "Inputs": tr["input"][:2200],
                "Target review to PREDICT (HIDDEN at inference)": tr["reference"][:1600],
                "Generated review": tr["generated"][:1600],
                "Feedback": (f"score={tr['score']:.2f}. {tr['metric_fb']} "
                             f"{traj_feedback(tr['stats'])} "
                             "Improve the ORCHESTRATOR prompt so the review MATCHES "
                             "THIS target reviewer's specific concerns, DEPTH, and "
                             "voice: delegate the RIGHT investigation subtasks to "
                             "surface the issues the target found (comparable coverage "
                             "if thorough, terse if terse). The orchestrator must keep "
                             "no file tools and delegate via subagent_type=code-explorer."),
            })
        return {comp: recs for comp in components_to_update}


def run(logins, profile="qwen", per_login=6, max_calls=None):
    data = gated_materialize(logins, per_login, profile)   # rubric-gated: substantive only
    if len(data) < 6:
        print(f"only {len(data)} instances; need >=6"); return None
    cut = max(4, int(len(data) * 2 / 3))
    tr, va = data[:cut], data[cut:]
    print(f"[gepa-oh] train={len(tr)} val={len(va)}", flush=True)
    adapter = OrchAdapter(profile)
    tag = f"{profile}_oh_" + "_".join(logins)[:36]
    run_dir = str(RESULTS / "runs" / tag)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    res = gepa.optimize(
        seed_candidate={POLICY_KEY: ORCH_SYS},
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
    out = PROMPTS / f"orch_policy.{profile}.txt"
    out.write_text(best)
    (RESULTS / f"gepa_oh_{profile}.json").write_text(json.dumps(
        {"logins": logins, "val_score": getattr(res, "val_aggregate_scores", None),
         "best_policy_path": str(out)}, indent=2, default=str))
    print(f"[gepa-oh] best orchestrator policy -> {out}", flush=True)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--logins", required=True)
    ap.add_argument("--profile", default="qwen")
    ap.add_argument("--per-login", type=int, default=6)
    ap.add_argument("--max-calls", type=int, default=None)
    a = ap.parse_args()
    run([l.strip() for l in a.logins.split(",") if l.strip()],
        a.profile, a.per_login, a.max_calls)
