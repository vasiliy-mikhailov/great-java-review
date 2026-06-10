"""CODE-GROUNDED point judge — a read-only OpenHands agent (grep/glob/file_editor) that
VERIFIES each review point against the actual repo @ base commit before scoring, so it
catches the fabrications a text-only judge cannot (e.g. 'releaseTarget throws' → read the
source; 'shade excludes native-image' → grep the build files).

Per candidate review: +1 good (correct AND useful, verified) / -1 wrong (fabricated or
false vs the code) / 0 trivial; then -1 per HUMAN point the candidate missed.

  ./venv-oh/bin/python -u src/point_judge_grounded.py            # smoke on captured PRs
"""
from __future__ import annotations
import json, os, re, sys, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, os.path.dirname(__file__))
import oh_delegate as od  # noqa: E402  registers tools, _NoViz, streaming patch via oh_review
from oh_review import _llm, _to_text  # noqa: E402
from agent_poc_batch import base_sha, ensure_repo  # noqa: E402
from openhands.sdk import Agent, Conversation, Tool  # noqa: E402
from openhands.sdk.event import MessageEvent, ActionEvent  # noqa: E402

JUDGE_SYS = """You GRADE a Java code review for SUBSTANCE against the ACTUAL repository,
which is checked out at the PR's BASE commit (the diff shows the proposed change; the NEW
code is NOT on disk yet). You have read-only tools: grep, glob, file_editor.

A good code review FINDS THINGS: real issues, bugs, risks, missing cases, violated
conventions, or concrete actionable improvements. PRAISE is NOT a finding.

For EACH distinct point in the CANDIDATE review:
1. VERIFY it against the real code. If it claims a library/framework method behaves a
   certain way (throws, is a no-op, returns null, …), or cites a file:line / pattern /
   precedent, USE YOUR TOOLS to read that code and check whether the claim is TRUE.
2. Score the point:
     "good"  (+1, or +2 if it is a CRITICAL/blocking issue — a real bug, data loss,
              broken-for-most-users, API break) = it identifies a REAL ISSUE or gives a
              concrete actionable improvement, AND is verified correct against the code.
     "wrong" (-1) = FABRICATED or factually FALSE about the code (you checked and it is
              not true), or cites code that does not exist.
     "trivial" (0) = PRAISE ("this is correct", "looks good", "valid JSON"), restating
              what the code does, or vague non-actionable advice. Confirming something is
              fine is NOT a contribution — score it 0.
   Set "severity" to "critical", "normal", or "praise/none".
Then read the HUMAN review's points; for each HUMAN point the candidate did NOT make,
that is a miss (-1).
net_score = (sum of candidate point scores) + (sum of miss penalties).

Be skeptical: a confident, specific claim you could NOT verify in the code is "wrong",
not "good". When done, output ONLY this JSON wrapped in <json></json> and stop:
<json>{"candidate":[{"point":"short","verdict":"good|wrong|trivial","severity":"critical|normal|none","score":1,"checked":"what you read"}],
"missed_human":["..."],"n_good":0,"n_wrong":0,"n_trivial":0,"n_missed":0,"net_score":0}</json>"""

_JSON_RE = re.compile(r"<json>(.*?)</json>", re.DOTALL | re.IGNORECASE)


def _extract(conv):
    ev = conv.state.events
    cand = []
    for a in reversed([e for e in ev if isinstance(e, ActionEvent)]):
        if getattr(a, "tool_name", None) == "finish":
            try:
                d = a.model_dump(); cand += [_to_text(d.get("thought")), _to_text(d.get("message"))]
            except Exception:  # noqa: BLE001
                pass
            break
    for m in [e for e in ev if isinstance(e, MessageEvent)
              and getattr(e, "source", None) == "agent"][-3:]:
        try:
            cand.append(_to_text([getattr(c, "text", "") for c in m.llm_message.content]))
        except Exception:  # noqa: BLE001
            pass
    for c in cand[::-1]:
        if not c:
            continue
        ms = _JSON_RE.findall(c)
        for blob in ms[::-1]:
            try:
                return json.loads(blob)
            except Exception:  # noqa: BLE001
                continue
        m = re.search(r"\{.*\}", c, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                pass
    return None


def grounded_judge(repo_dir, pr_input, human, candidate, profile="qwen", max_steps=45,
                   trace_path=None):
    od._register_subagents()   # registers grep/glob/file_editor
    llm = _llm(profile)
    tools = [Tool(name="grep"), Tool(name="glob"), Tool(name="file_editor")]
    agent = Agent(llm=llm, tools=tools, system_prompt=JUDGE_SYS, condenser=od._condenser(llm))
    state = {"n": 0, "conv": None}

    def cap(e):
        if isinstance(e, ActionEvent):
            state["n"] += 1
            if state["n"] >= max_steps and state["conv"]:
                try:
                    state["conv"].pause()
                except Exception:  # noqa: BLE001
                    pass
    conv = Conversation(agent=agent, workspace=str(repo_dir), visualizer=od._NoViz(),
                        callbacks=[cap])
    state["conv"] = conv
    try:
        conv.send_message(
            f"PR (diff):\n{pr_input[:16000]}\n\nHUMAN REVIEW (gold):\n{human}\n\n"
            f"CANDIDATE REVIEW TO GRADE:\n{candidate}\n\nVerify each candidate point against "
            "the repo with your tools, then output ONLY the <json>...</json>.")
        conv.run()
        res = _extract(conv)
        if res is None:                 # ran out of steps / didn't emit JSON — force it
            state["n"] = 0
            try:
                conv.send_message("Stop verifying. Output the final scoring NOW as ONLY the "
                                  "<json>...</json> block (no prose), based on what you have.")
                conv.run()
                res = _extract(conv)
            except Exception:  # noqa: BLE001
                pass
        return res
    finally:
        if trace_path:                       # full judge verification trace
            od.dump_events(conv, trace_path)
        try:
            conv.close()
        except Exception:  # noqa: BLE001
            pass


def smoke():
    data = []
    for fn in ("results/qual_capture.json", "results/qual_capture2.json"):
        try:
            data += json.load(open(fn))
        except Exception:  # noqa: BLE001
            pass
    print(f"{'PR':24} {'cond':9} {'net':>4} {'good':>4} {'wrong':>5} {'miss':>4}", flush=True)
    print("-" * 60, flush=True)
    out = []
    for r in data:
        repo, pr = r["repo"], r["pr"]
        d = ensure_repo(repo, base_sha(repo, pr))
        for cond in ("diff_only", "mr_code"):
            res = None
            for _att in range(3):               # retry on parse-fail (nondeterministic)
                res = grounded_judge(str(d), r["pr_input"], r["human"], r[cond])
                if res:
                    break
                print(f"    {repo.split('/')[-1]}#{pr} {cond} parse-fail, retry…", flush=True)
            tag = repo.split("/")[-1] + "#" + str(pr)
            if not res:
                print(f"{tag:24} {cond:9}  JUDGE PARSE FAIL (3x)", flush=True); continue
            print(f"{tag:24} {cond:9} {res.get('net_score',0):>4} {res.get('n_good',0):>4} "
                  f"{res.get('n_wrong',0):>5} {res.get('n_missed',0):>4}", flush=True)
            out.append({"pr": tag, "cond": cond, **{k: res.get(k) for k in
                        ("net_score", "n_good", "n_wrong", "n_trivial", "n_missed")},
                        "detail": res.get("candidate")})
            json.dump(out, open("results/point_judge_grounded.json", "w"), indent=2)


if __name__ == "__main__":
    smoke()
