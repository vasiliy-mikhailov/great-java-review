"""Generate reviews for a set of PRs with the delegation harness, recording per-PR
net (left for external Claude judging) / sec / sent / recv / calls plus full traces.
Resumable: PRs already present in the output file are skipped.

  ./venv-oh/bin/python -u src/v8/runner.py quarkus:34681   # one PR
  ./venv-oh/bin/python -u src/v8/runner.py 37              # first 37 of the PR set

Configured by env: V8_PRS (input PR set), V8_OUT (output json), V8_TRACE_DIR (traces).
"""
from __future__ import annotations
import json, os, sys, time, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ on path
from v8 import token_meter as tm  # noqa: E402
tm.install()
from v8 import call_log  # noqa: E402
call_log.install()
from v8.harness import oh_review_delegate  # noqa: E402
from v8.full_diff import full_pr_input  # noqa: E402
from v8 import pr_diff_tool  # noqa: E402
from v8.repo import base_sha, ensure_repo  # noqa: E402
import dataset as ds  # noqa: E402

PRS = os.environ.get("V8_PRS", "results/threeway_prs.json")
OUT = os.environ.get("V8_OUT", "results/threeway_v8.json")
TRACE_DIR = os.environ.get("V8_TRACE_DIR", "results/traces_v8")
MIN = 200


def _select(args, prs):
    if len(args) == 1 and args[0].isdigit():
        return prs[: int(args[0])]
    want = {int(a.split(":")[-1]) for a in args}
    return [x for x in prs if x["pr"] in want] or prs[:1]


def main():
    prs = json.load(open(PRS))
    sel = _select(sys.argv[1:], prs)
    imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values() for x in v}
    done = {(r["repo"], r["pr"]): r for r in (json.load(open(OUT)) if os.path.exists(OUT) else [])}
    out = list(done.values())
    os.makedirs(TRACE_DIR, exist_ok=True)
    print(f"delegation harness on {len(sel)} PR(s)\n", flush=True)
    for p in sel:
        repo, pr = p["repo"], p["pr"]
        if (repo, pr) in done:
            print(f"== {repo}#{pr} already done, skip", flush=True); continue
        x = imap.get((repo, pr))
        if not x:
            print(f"not found {repo}#{pr}", flush=True); continue
        pi = x["input"]
        bsha = base_sha(repo, pr)
        d = str(ensure_repo(repo, bsha))
        pi, ok = full_pr_input(pi, d, repo, pr, bsha)
        print(f"  full-diff: {'OK, ' + format(len(pi), ',') + ' chars' if ok else 'FALLBACK to dataset input'}", flush=True)
        tgt = pr_diff_tool.set_pr(d, bsha, pr)
        print(f"  pr tools target: {tgt or 'UNAVAILABLE'}", flush=True)
        files = pr_diff_tool.changed_files()
        if files:   # complete file list replaces the dataset header's capped one
            import re
            pi = re.sub(r'Changed files \((\d+)\):[^\n]*',
                        lambda m: f"Changed files ({m.group(1)}): " + ", ".join(files),
                        pi, count=1)
            print(f"  complete file list: {len(files)} files", flush=True)
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
        rec = {"repo": repo, "pr": pr, "reviewer": p.get("reviewer"),
               "net": None,            # left for external Claude judging (see AGENTS.md)
               "sec": sec, "sent": sent, "recv": recv, "calls": ncalls,
               "text": rv, "judge": None}
        out = [r for r in out if (r["repo"], r["pr"]) != (repo, pr)] + [rec]
        json.dump(out, open(OUT, "w"), indent=2)
        flag = "" if len(rv) >= MIN else "  <-- SHORT/EMPTY"
        print(f"== {repo.split('/')[-1]}#{pr}: {len(rv)} chars  {sec}s  sent {sent:,}  calls {ncalls}{flag}", flush=True)


if __name__ == "__main__":
    main()
