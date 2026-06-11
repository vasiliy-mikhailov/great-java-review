"""A/B the v3 subagent toolset (search + W3 focus) against the frozen baseline AND v2,
on the SAME PRs / same fixed order. Records net / sec / sent / recv / calls + traces.
Resumable.

  ./venv-oh/bin/python -u src/tools_v3.py quarkus:28314   # smoke one PR
  ./venv-oh/bin/python -u src/tools_v3.py 37              # full run
"""
from __future__ import annotations
import os
os.environ["OH_SEARCH_V2"] = "1"          # MUST precede oh_delegate import
os.environ["OH_FOCUS"] = "1"              # v3 = search + focus (W3)
import json, sys, time, warnings          # noqa: E402
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import token_meter as tm  # noqa: E402
tm.install()
import call_log  # noqa: E402
call_log.install()
import point_judge_grounded as g  # noqa: E402
from oh_delegate import oh_review_delegate, _V2, _FOCUS  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
import dataset as ds  # noqa: E402

PRS = "results/threeway_prs.json"
OUT = "results/threeway_v3.json"
TRACE_DIR = "results/traces_v3"
BASE = "results/threeway.json"
V2 = "results/threeway_v2.json"
MIN = 200


def _select(args, prs):
    if len(args) == 1 and args[0].isdigit():
        return prs[: int(args[0])]
    want = {int(a.split(":")[-1]) for a in args}
    return [x for x in prs if x["pr"] in want] or prs[:1]


def _judge(d, pi, human, cand, tp, attempts=3):
    for _ in range(attempts):
        r = g.grounded_judge(d, pi, human, cand, trace_path=tp)
        if r:
            return r
        print("      judge parse-fail, retry…", flush=True)
    return None


def main():
    assert _V2 and _FOCUS, "OH_SEARCH_V2/OH_FOCUS not active — v3 toolset not wired!"
    prs = json.load(open(PRS))
    sel = _select(sys.argv[1:], prs)
    imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values() for x in v}
    base = {(r["repo"], r["pr"]): r for r in (json.load(open(BASE)) if os.path.exists(BASE) else [])}
    v2 = {(r["repo"], r["pr"]): r for r in (json.load(open(V2)) if os.path.exists(V2) else [])}
    done = {(r["repo"], r["pr"]): r for r in (json.load(open(OUT)) if os.path.exists(OUT) else [])}
    out = list(done.values())
    os.makedirs(TRACE_DIR, exist_ok=True)
    print(f"v3 (search+focus) A/B on {len(sel)} PR(s)\n", flush=True)
    for p in sel:
        repo, pr = p["repo"], p["pr"]
        if (repo, pr) in done:
            print(f"== {repo}#{pr} already done (v3), skip", flush=True); continue
        x = imap.get((repo, pr))
        if not x:
            print(f"not found {repo}#{pr}", flush=True); continue
        pi, human = x["input"], x["reference_review"]
        d = str(ensure_repo(repo, base_sha(repo, pr)))
        tag = repo.replace("/", "__") + "__" + str(pr)
        clog = os.path.join(TRACE_DIR, tag + "__calls.jsonl"); open(clog, "w").close()
        call_log.set_path(clog)
        p0, c0 = tm.total(); t0 = time.monotonic()
        try:
            rv, _ = oh_review_delegate(d, pi, trace_path=os.path.join(TRACE_DIR, tag + "__orch.json"))
        except Exception as e:  # noqa: BLE001
            print(f"  {repo}#{pr} EXC: {e}", flush=True); rv = ""
        sec = round(time.monotonic() - t0, 1)
        p1, c1 = tm.total()
        sent, recv = p1 - p0, c1 - c0
        ncalls = sum(1 for _ in open(clog))
        jr = _judge(d, pi, human, rv, os.path.join(TRACE_DIR, tag + "__judge.json")) \
            if len(rv.strip()) >= MIN else None
        net = (jr or {}).get("net_score")
        rec = {"repo": repo, "pr": pr, "reviewer": p.get("reviewer"),
               "net": net, "sec": sec, "sent": sent, "recv": recv, "calls": ncalls,
               "text": rv, "judge": jr}
        out = [r for r in out if (r["repo"], r["pr"]) != (repo, pr)] + [rec]
        json.dump(out, open(OUT, "w"), indent=2)
        bt = (base.get((repo, pr), {}).get("mr_code_tools") or {})
        bsent = (bt.get("tok") or {}).get("prompt")
        v2r = v2.get((repo, pr)) or {}
        print(f"== {repo.split('/')[-1]}#{pr}", flush=True)
        print(f"   v3 (search+focus): net {net}  {sec}s  sent {sent:,}  calls {ncalls}", flush=True)
        if v2r:
            print(f"   v2 (search only) : net {v2r.get('net')}  sent {v2r.get('sent'):,}  calls {v2r.get('calls')}", flush=True)
        if bsent is not None:
            print(f"   baseline (grep)  : net {bt.get('net')}  sent {bsent:,}", flush=True)


if __name__ == "__main__":
    main()
