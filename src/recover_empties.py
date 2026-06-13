"""Recover 'empty' v8 reviews from their saved orchestrator traces.

Root cause (see REPORT 'empty generation' analysis): the harness extracted the
finish action's review from a top-level `message` key, but the finish tool nests
its message under `action.message`. So finish-via-tool reviews were lost and stored
as "". The full review is in the trace — recover it deterministically, no rerun.

  python3 src/recover_empties.py results/threeway_v8_elite.json results/traces_v8_elite
"""
from __future__ import annotations
import json, re, sys


def _to_text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join((c.get("text", "") if isinstance(c, dict) else str(c)) for c in v)
    return str(v)


def _tagged(text):
    if "<review>" not in text:
        return ""
    body = text[text.rfind("<review>") + len("<review>"):]
    return body.replace("</review>", "").strip()


def recover_from_trace(trace_path):
    """Return the review text from the last finish action's action.message
    (falls back to top-level message / latest agent message), or ''."""
    events = json.load(open(trace_path))
    # last finish ActionEvent
    for e in reversed([x for x in events if x.get("type") == "ActionEvent"]):
        if e.get("tool_name") == "finish":
            msg = e.get("message")
            if msg is None:
                msg = (e.get("action") or {}).get("message")
            txt = _to_text(msg)
            t = _tagged(txt)
            if t:
                return t
            if "SUMMARY:" in txt:
                return txt.strip()
            break
    return ""


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "results/threeway_v8_elite.json"
    trace_dir = sys.argv[2] if len(sys.argv) > 2 else "results/traces_v8_elite"
    recs = json.load(open(out_path))
    recovered, still_empty = [], []
    for r in recs:
        if len(r.get("text", "")) >= 200:
            continue
        tag = r["repo"].replace("/", "__") + "__" + str(r["pr"])
        tp = f"{trace_dir}/{tag}__orch.json"
        try:
            txt = recover_from_trace(tp)
        except FileNotFoundError:
            still_empty.append((r["repo"], r["pr"], "no-trace"))
            continue
        if len(txt) >= 200:
            r["text"] = txt
            recovered.append((r["repo"], r["pr"], len(txt)))
        else:
            still_empty.append((r["repo"], r["pr"], "trace-empty"))
    if recovered:
        json.dump(recs, open(out_path, "w"), indent=2)
    print(f"recovered {len(recovered)}: {recovered}")
    print(f"still empty {len(still_empty)}: {still_empty}")


if __name__ == "__main__":
    main()
