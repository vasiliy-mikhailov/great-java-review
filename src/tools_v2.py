"""A/B the `search`-equipped subagent toolset (mr_code_tools_v2) against the baseline's
mr_code_tools, on the SAME PRs. Records net / sec / sent / recv / LLM-calls, full traces,
and per-call logs (to measure the turn-count drop). Resumable.

  ./venv-oh/bin/python -u src/tools_v2.py 1            # smoke: first 1 PR
  ./venv-oh/bin/python -u src/tools_v2.py dubbo:13489  # a specific PR
  ./venv-oh/bin/python -u src/tools_v2.py 27           # spread to 27 PRs
"""
from __future__ import annotations
import os
os.environ["OH_SEARCH_V2"] = "1"          # MUST precede oh_delegate import (_V2 read there)
import json, sys, time, warnings          # noqa: E402
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import token_meter as tm  # noqa: E402
tm.install()
import call_log  # noqa: E402
call_log.install()                        # register once; we switch path per-PR
from oh_delegate import oh_review_delegate, _V2  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
import dataset as ds  # noqa: E402

PRS = "results/threeway_prs.json"
OUT = "results/threeway_v2.json"
TRACE_DIR = "results/traces_v2"
BASE = "results/threeway.json"
MIN = 200


def _select(args, prs):
    if len(args) == 1 and args[0].isdigit():
        return prs[: int(args[0])]
    want = {int(a.split(":")[-1]) for a in args}
    return [x for x in prs if x["pr"] in want] or prs[:1]


def main():
    assert _V2, "OH_SEARCH_V2 not active — search tool won't be wired!"
    prs = json.load(open(PRS))
    sel = _select(sys.argv[1:], prs)
    imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values() for x in v}
    base = {}
    if os.path.exists(BASE):
        for r in json.load(open(BASE)):
            base[(r["repo"], r["pr"])] = r
    done = {}
    if os.path.exists(OUT):
        for r in json.load(open(OUT)):
            done[(r["repo"], r["pr"])] = r
    out = list(done.values())
    os.makedirs(TRACE_DIR, exist_ok=True)
    print(f"v2 A/B on {len(sel)} PR(s)  (search tool wired into subagents)\n", flush=True)
    for p in sel:
        repo, pr = p["repo"], p["pr"]
        if (repo, pr) in done:
            print(f"== {repo}#{pr} already done (v2), skip", flush=True); continue
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
        jr = None   # judging removed: Claude re-judges stored texts (see AGENTS.md)
        net = (jr or {}).get("net_score")
        rec = {"repo": repo, "pr": pr, "reviewer": p.get("reviewer"),
               "net": net, "sec": sec, "sent": sent, "recv": recv, "calls": ncalls,
               "text": rv, "judge": jr}
        out = [r for r in out if (r["repo"], r["pr"]) != (repo, pr)] + [rec]
        json.dump(out, open(OUT, "w"), indent=2)
        b = base.get((repo, pr), {}).get("mr_code_tools", {})
        bnet, bsec = b.get("net"), b.get("sec")
        btok = b.get("tok") or {}
        bsent = btok.get("prompt")
        print(f"== {repo.split('/')[-1]}#{pr}", flush=True)
        print(f"   v2:       net {net}  {sec}s  sent {sent:,}  recv {recv:,}  calls {ncalls}", flush=True)
        print(f"   baseline: net {bnet}  {bsec}s  sent {bsent:,}" if bsent else
              "   baseline: (no baseline record yet)", flush=True)
        if bsent and sent:
            print(f"   -> sent {bsent/sent:.1f}x less, time {(bsec or 0)/sec:.1f}x"
                  f"{'' if bnet is None else f', net {net}-vs-{bnet}'}", flush=True)


if __name__ == "__main__":
    main()
