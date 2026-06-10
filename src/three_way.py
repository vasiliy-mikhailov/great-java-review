"""Unified 3-way grounded comparison with WALL-CLOCK TIMING, resumable.

For each sampled PR (results/threeway_prs.json) it generates all three rungs, timing
each, then code-grounded-judges each:
  mr            = diff_only_review        (diff hunks only, 1 call)
  mr_code       = mr_code_review          (diff + full changed files, 1 call, no tools)
  mr_code_tools = oh_review_delegate      (+ grep/glob + delegation, multi-step agent)

Results -> results/threeway.json (one record per PR, with .sec and .judge per cond).
Resumable: a PR already fully present (3 judged conds) is skipped; partial PRs redo
only the missing conds. Flaky endpoint is ridden out in-run (retry on empty/error).

  ./venv-oh/bin/python -u src/three_way.py
"""
from __future__ import annotations
import json, os, sys, time, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from agent_review import diff_only_review  # noqa: E402
from oh_delegate import mr_code_review, oh_review_delegate  # noqa: E402
from paired_compare import _wait_for_endpoint  # noqa: E402
import point_judge_grounded as g  # noqa: E402
import token_meter as tm  # noqa: E402
tm.install()

PRS = "results/threeway_prs.json"
OUT = "results/threeway.json"
TRACE_DIR = "results/traces"     # full agent/judge traces, one file per PR×cond
MIN = 200  # chars; below this a "review" is junk/empty (endpoint hiccup)


def _save_raw(path):
    """Persist the single-call exchange (messages sent + raw completion WITH thinking)
    for mr / mr_code, mirroring the event-log traces of the agent rungs."""
    import llm_client as lc
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump({"messages": lc.LAST.get("messages"), "raw": lc.LAST.get("raw"),
                   "usage": lc.LAST.get("usage")}, open(path, "w"), indent=1, default=str)
    except Exception:  # noqa: BLE001
        pass


def _mr(d, pi, tp):
    rv = diff_only_review(pi); _save_raw(tp); return rv


def _mr_code(d, pi, tp):
    rv = mr_code_review(d, pi); _save_raw(tp); return rv


def _mr_code_tools(d, pi, tp):
    rv, _ = oh_review_delegate(d, pi, trace_path=tp); return rv


CONDS = [("mr", _mr), ("mr_code", _mr_code), ("mr_code_tools", _mr_code_tools)]


def _trace(repo, pr, suffix):
    return os.path.join(TRACE_DIR, f"{repo.replace('/', '__')}__{pr}__{suffix}.json")


def _gen(label, fn, d, pi, tp, attempts=3):
    """Generate one review, timing + token-counting it; retry on empty/error.
    tp = trace path passed through to the condition (event log / raw exchange)."""
    for a in range(attempts):
        _wait_for_endpoint()
        p0, c0 = tm.total()
        t0 = time.monotonic()
        try:
            out = fn(d, pi, tp)
            rv = out[0] if isinstance(out, tuple) else out
        except Exception as e:  # noqa: BLE001
            print(f"    {label} attempt {a+1}/{attempts} EXC: {e}", flush=True); rv = ""
        sec = round(time.monotonic() - t0, 1)
        p1, c1 = tm.total()
        tok = {"prompt": p1 - p0, "completion": c1 - c0, "total": (p1 - p0) + (c1 - c0)}
        if rv and len(rv.strip()) >= MIN:
            if a:
                print(f"    {label} recovered on attempt {a+1}", flush=True)
            return rv, sec, tok
        print(f"    {label} attempt {a+1}/{attempts} empty/short "
              f"(len={len(rv.strip()) if rv else 0}, {sec}s) — retry", flush=True)
    return rv or "", sec, tok


def _judge(d, pi, human, cand, tp=None, attempts=3):
    for _ in range(attempts):
        res = g.grounded_judge(d, pi, human, cand, trace_path=tp)
        if res:
            return res
        print("      judge parse-fail, retry…", flush=True)
    return None


def main():
    prs = json.load(open(PRS))
    done = {}
    if os.path.exists(OUT):
        for r in json.load(open(OUT)):
            done[(r["repo"], r["pr"])] = r
    out = list(done.values())
    for p in prs:
        repo, pr = p["repo"], p["pr"]
        rec = done.get((repo, pr), {"repo": repo, "pr": pr, "reviewer": p.get("reviewer")})
        if all(rec.get(c, {}).get("judge") for c, _ in CONDS):
            print(f"== {repo}#{pr} already complete, skip", flush=True); continue
        tag = repo.split("/")[-1] + "#" + str(pr)
        print(f"== {tag} ({p.get('reviewer')}) ==", flush=True)
        d = str(ensure_repo(repo, base_sha(repo, pr)))
        # need pr_input + human — reuse stored if resuming, else fetch from dataset
        if not rec.get("pr_input"):
            import dataset as ds
            imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values()
                    for x in v}
            x = imap[(repo, pr)]
            rec["pr_input"], rec["human"] = x["input"], x["reference_review"]
        pi, human = rec["pr_input"], rec["human"]
        for c, fn in CONDS:
            if rec.get(c, {}).get("judge"):
                continue
            gen_tp = _trace(repo, pr, c)
            judge_tp = _trace(repo, pr, c + "__judge")
            rv, sec, tok = _gen(c, fn, d, pi, gen_tp)
            jr = _judge(d, pi, human, rv, judge_tp) if len(rv.strip()) >= MIN else None
            rec[c] = {"text": rv, "sec": sec, "tok": tok, "judge": jr,
                      "net": (jr or {}).get("net_score"),
                      "trace": gen_tp, "judge_trace": judge_tp}
            print(f"    {c:14} {sec:>6}s  {tok['total']:>7}tok  "
                  f"net {(jr or {}).get('net_score')}", flush=True)
            out = [r for r in out if (r["repo"], r["pr"]) != (repo, pr)] + [rec]
            json.dump(out, open(OUT, "w"), indent=2)
        done[(repo, pr)] = rec
    _summary(out)


def _summary(out):
    def k(x):
        return (str(round(x / 1000)) + "k") if x else "-"
    print("\n" + "=" * 96, flush=True)
    print("per cell: net / sec / SENT_tok / RECV_tok", flush=True)
    print(f"{'PR':24} {'mr':>22} {'mr_code':>22} {'mr_code_tools':>22}", flush=True)
    tot = {c: [0, 0.0, 0, 0, 0] for c, _ in CONDS}  # net, sec, sent, recv, n_tok
    for r in sorted(out, key=lambda r: r["repo"]):
        cells = []
        for c, _ in CONDS:
            cc = r.get(c, {})
            n, s = cc.get("net"), cc.get("sec")
            tk = cc.get("tok") or {}
            sent, recv = tk.get("prompt"), tk.get("completion")
            if n is not None:
                tot[c][0] += n
            if s:
                tot[c][1] += s
            if sent or recv:
                tot[c][2] += sent or 0; tot[c][3] += recv or 0; tot[c][4] += 1
            cells.append(f"{n if n is not None else '-':>3}/{int(s) if s else '-':>4}/"
                         f"{k(sent):>4}/{k(recv):>4}")
        tag = r["repo"].split("/")[-1] + "#" + str(r["pr"])
        print(f"{tag:24} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22}", flush=True)
    print("-" * 96, flush=True)
    for c, _ in CONDS:
        net, sec, sent, recv, ntk = tot[c]
        n = ntk or 1
        print(f"  {c:14} net {net:>4}   {sec:>6.0f}s   "
              f"sent {sent:>9,} (avg {sent//n:>7,})   "
              f"recv {recv:>9,} (avg {recv//n:>7,})   n={ntk}", flush=True)


if __name__ == "__main__":
    main()
