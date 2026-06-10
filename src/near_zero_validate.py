"""Validate the <review> extraction fix on the PRs that previously near-zeroed
(finish-with-preamble stalls). For each rollout, capture whether the finish action
was a preamble-stall and whether the fix STILL extracted a real review (= recovery).

  ./venv-oh/bin/python -u src/near_zero_validate.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from oh_review import _to_text  # noqa: E402
from oh_delegate import oh_review_delegate  # noqa: E402
from openhands.sdk import LocalConversation  # noqa: E402
from openhands.sdk.event import ActionEvent  # noqa: E402

# previously near-zero rollouts; (repo, pr, n_attempts)
TARGETS = [("spring-projects/spring-boot", 50273, 3),   # stalled in deps exp (0.033)
           ("quarkiverse/quarkus-mcp-server", 703, 2),  # historic 0.0 case
           ("apache/pulsar", 25883, 1)]                 # sanity (a non-staller)

snap = {}
_oc = LocalConversation.close


def _close(self, *a, **k):
    try:
        snap["events"] = list(self.state.events)
    except Exception:  # noqa: BLE001
        pass
    return _oc(self, *a, **k)


LocalConversation.close = _close


def _finish_raw(events):
    for a in reversed([e for e in events if isinstance(e, ActionEvent)]):
        if getattr(a, "tool_name", None) == "finish":
            d = a.model_dump()
            return _to_text(d.get("message")), _to_text(d.get("thought"))
    return "", ""


def main():
    inst = ds.build_instances()
    imap = {(x["repo"], str(x["pr"])): x for v in inst.values() for x in v}
    rows = []
    for repo, pr, n in TARGETS:
        x = imap.get((repo, str(pr)))
        if not x:
            print(f"SKIP {repo}#{pr} not found", flush=True); continue
        sha = base_sha(repo, pr); d = ensure_repo(repo, sha)
        for att in range(n):
            snap.clear()
            review, trace = oh_review_delegate(str(d), x["input"])
            msg, th = _finish_raw(snap.get("events", []))
            score, _ = mt.score_with_feedback(x["input"], review, x["reference_review"])
            msg_is_preamble = ("SUMMARY:" not in msg and "POINTS:" not in msg
                               and "<review>" not in msg.lower())
            stalled_finish = bool(msg.strip()) and msg_is_preamble and len(msg) < 400
            got_review = len(review.strip()) > 200 and ("SUMMARY:" in review or "POINTS:" in review)
            recovered = stalled_finish and got_review
            rows.append({"pr": f"{repo.split('/')[-1]}#{pr}", "att": att + 1,
                         "score": round(score, 4), "review_len": len(review.strip()),
                         "finish_msg_len": len(msg), "finish_msg_head": msg[:80],
                         "stalled_finish": stalled_finish, "got_review": got_review,
                         "RECOVERED": recovered})
            print(f"  {repo.split('/')[-1]}#{pr} att{att+1}: score={score:.3f} "
                  f"review_len={len(review.strip())} finish_msg={msg[:50]!r} "
                  f"stalled_finish={stalled_finish} RECOVERED={recovered}", flush=True)
            json.dump(rows, open("results/near_zero_validate.json", "w"), indent=2)
    n_stall = sum(r["stalled_finish"] for r in rows)
    n_rec = sum(r["RECOVERED"] for r in rows)
    n_zero = sum(r["score"] < 0.05 for r in rows)
    print(f"\n=== {len(rows)} rollouts: {n_stall} finish-preamble stalls, "
          f"{n_rec} RECOVERED, {n_zero} still near-zero ===", flush=True)


if __name__ == "__main__":
    main()
