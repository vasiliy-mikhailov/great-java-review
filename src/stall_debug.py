"""Dig into the 'finish with preamble' stall: run the spring-boot#50273 rollout and
dump the FULL finish action (message + thought + all fields) and the last agent
message + raw, so we can see WHERE the review went when the visible review is empty.

  ./venv-oh/bin/python -u src/stall_debug.py
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
import oh_review  # noqa: E402
from oh_review import _to_text, _post_think  # noqa: E402
from oh_delegate import oh_review_delegate, ORCH_SYS  # noqa: E402
from openhands.sdk.event import MessageEvent, ActionEvent  # noqa: E402

# monkeypatch oh_review_delegate is complex; instead replicate the tail: we hook by
# running the delegate and then re-reading conv.state — but the conv is closed inside.
# Simpler: set OH_DEBUG and also patch _extract path by capturing via a wrapper.
os.environ["OH_DEBUG"] = "1"


def main():
    inst = ds.build_instances()
    x = next(v for vs in inst.values() for v in vs
             if v["repo"] == "spring-projects/spring-boot" and str(v["pr"]) == "50273")
    sha = base_sha(x["repo"], x["pr"]); d = ensure_repo(x["repo"], sha)
    pr_input = x["input"]

    # we need the raw events — patch LocalConversation.close to snapshot events first
    from openhands.sdk import LocalConversation
    snap = {}
    _orig_close = LocalConversation.close

    def _close(self, *a, **k):
        try:
            snap["events"] = list(self.state.events)
        except Exception as e:  # noqa: BLE001
            snap["err"] = str(e)
        return _orig_close(self, *a, **k)
    LocalConversation.close = _close

    review, trace = oh_review_delegate(str(d), pr_input)
    print(f"\n=== visible review len={len(review.strip())} ===", flush=True)

    ev = snap.get("events", [])
    out = {"visible_review": review, "trace": [t for t, _ in trace], "finish_actions": [],
           "last_agent_messages": []}
    for a in ev:
        if isinstance(a, ActionEvent) and getattr(a, "tool_name", None) == "finish":
            dd = a.model_dump()
            out["finish_actions"].append({k: _to_text(v) if k in ("message", "thought") else str(v)[:200]
                                          for k, v in dd.items() if k in ("message", "thought", "tool_name")})
    amsgs = [e for e in ev if isinstance(e, MessageEvent) and getattr(e, "source", None) == "agent"]
    for m in amsgs[-3:]:
        try:
            txt = _to_text([getattr(c, "text", "") for c in m.llm_message.content])
        except Exception:  # noqa: BLE001
            txt = str(m)
        out["last_agent_messages"].append({"len": len(txt), "has_SUMMARY": "SUMMARY:" in txt,
                                           "has_POINTS": "POINTS:" in txt, "text_head": txt[:500],
                                           "text_tail": txt[-500:]})
    json.dump(out, open("results/stall_debug.json", "w"), indent=2)
    print("=== finish actions (message vs thought) ===", flush=True)
    for fa in out["finish_actions"]:
        print(f"  message(len {len(fa.get('message',''))}): {fa.get('message','')[:300]!r}", flush=True)
        th = fa.get("thought", "")
        print(f"  thought(len {len(th)}) has_SUMMARY={'SUMMARY:' in th} has_POINTS={'POINTS:' in th}: {th[:300]!r}", flush=True)
    print(f"=== {len(amsgs)} agent messages; last-3 SUMMARY/POINTS presence above in json ===", flush=True)


if __name__ == "__main__":
    main()
