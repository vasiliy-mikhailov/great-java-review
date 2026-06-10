"""Validate the <review>-tag extraction fix on a small/fast PR: run a rollout, then
check (a) the model emitted <review> tags, (b) extraction returned a clean review.

  ./venv-oh/bin/python -u src/validate_fix.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
from wide_dataset import quality_key  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from oh_review import _to_text  # noqa: E402
from oh_delegate import oh_review_delegate, _tagged  # noqa: E402
from openhands.sdk import LocalConversation  # noqa: E402
from openhands.sdk.event import ActionEvent  # noqa: E402

snap = {}
_oc = LocalConversation.close


def _close(self, *a, **k):
    try:
        snap["events"] = list(self.state.events)
    except Exception:  # noqa: BLE001
        pass
    return _oc(self, *a, **k)


LocalConversation.close = _close


def main():
    gold = set(json.load(open("data/cache/clean_both_technical.json")))
    inst = ds.build_instances()
    # small, fast repo
    x = next(v for vs in inst.values() for v in vs
             if v["repo"] == "agroal/agroal"
             and quality_key(v["repo"], v["pr"], v["review_id"]) in gold)
    print(f"validating on {x['repo']}#{x['pr']}", flush=True)
    sha = base_sha(x["repo"], x["pr"]); d = ensure_repo(x["repo"], sha)
    review, trace = oh_review_delegate(str(d), x["input"])

    ev = snap.get("events", [])
    finish_raw = ""
    for a in reversed([e for e in ev if isinstance(e, ActionEvent)]):
        if getattr(a, "tool_name", None) == "finish":
            dd = a.model_dump()
            finish_raw = _to_text(dd.get("thought")) + "\n" + _to_text(dd.get("message"))
            break
    print("\n===== VALIDATION =====", flush=True)
    print("trace:", [t for t, _ in trace], flush=True)
    print("model emitted <review> tag:", "<review>" in finish_raw.lower(), flush=True)
    print("count of <review> in finish turn:", finish_raw.lower().count("<review>"), flush=True)
    print("extracted review len:", len(review.strip()),
          " has SUMMARY:", "SUMMARY:" in review, " has POINTS:", "POINTS:" in review, flush=True)
    print("extraction matches LAST tag:", _tagged(finish_raw).strip()[:60] == review.strip()[:60]
          if "<review>" in finish_raw.lower() else "n/a (no tag)", flush=True)
    print("\n----- REVIEW -----\n" + review[:1600], flush=True)


if __name__ == "__main__":
    main()
