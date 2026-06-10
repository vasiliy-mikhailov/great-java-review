"""Attempt 2 PoC — agentic review with repo access.

Give Qwen a minimal ReAct tool loop (ls / read_file / grep, sandboxed to a repo
checked out at the PR's base commit) so it can read the SURROUNDING code (intent,
conventions, existing impls) before writing its review — the context P10's first
pass said agreeing humans rely on. Compare to the diff-only baseline (Attempt 1),
both scored vs the human review with the fixed metric.

Usage: python src/agent_review.py <repo_dir> <repo> <pr>   # pr present in excellent_reviews.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402
import metric as mt  # noqa: E402
from llm_client import get_llm, final_review  # noqa: E402

MAX_STEPS = 200       # NOT a target — a high safety ceiling. 128k ctx leaves room;
#                       the agent (and GEPA-evolved policy) should self-terminate via
#                       ACTION: review long before this. The real budget is learned,
#                       not the cap.


# ---- sandboxed repo tools --------------------------------------------------
def _safe(repo: Path, rel: str) -> Path | None:
    try:
        p = (repo / rel).resolve()
        p.relative_to(repo.resolve())   # must stay inside the repo
        return p
    except Exception:  # noqa: BLE001
        return None


def tool_ls(repo: Path, arg: str) -> str:
    p = _safe(repo, arg or ".")
    if not p or not p.exists():
        return f"(no such dir: {arg})"
    if p.is_file():
        return f"{arg} is a file ({p.stat().st_size} bytes)"
    items = sorted(os.listdir(p))[:200]
    return "\n".join(items)


def tool_read(repo: Path, arg: str) -> str:
    p = _safe(repo, arg)
    if not p or not p.is_file():
        return f"(no such file: {arg})"
    return p.read_text(errors="replace")          # full file, no truncation (128k ctx)


def tool_grep(repo: Path, arg: str) -> str:
    # tolerate the model's natural `grep [flags] <pattern> [path]` usage
    import shlex
    try:
        toks = shlex.split(arg)
    except Exception:  # noqa: BLE001
        toks = arg.split()
    rest = [t for t in toks if not t.startswith("-")]
    if not rest:
        return "(no pattern)"
    pattern = rest[0]
    subtree = str(repo)
    if len(rest) > 1:                       # optional path subtree, sandboxed
        p = _safe(repo, rest[1])
        if p and p.exists():
            subtree = str(p)
    try:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.java", "-m", "40", pattern, subtree],
            capture_output=True, text=True, timeout=20).stdout
    except Exception as e:  # noqa: BLE001
        return f"(grep error: {e})"
    out = out.replace(str(repo) + "/", "")
    lines = out.splitlines()[:40]
    return "\n".join(lines) if lines else "(no matches)"


# ---- repomap: ranked structural map (OpenHands/aider idea, dependency-free) ----
_DECL = re.compile(
    r"(?m)^[ \t]*(?:public|protected|private|abstract|final|sealed|static|strictfp|\s)*"
    r"\b(class|interface|enum|record)\s+([A-Z]\w*)")
_METH = re.compile(
    r"(?m)^[ \t]*(?:public|protected|private)\s+"
    r"(?:static\s+|final\s+|abstract\s+|synchronized\s+|default\s+|native\s+)*"
    r"[\w<>\[\],.?]+\s+(\w+)\s*\(([^;{]*)\)\s*(?:throws[^{;]+)?\{")
_SKIP = ("/.git", "/target", "/build", "/node_modules", "/.idea")


def _java_files(repo: Path):
    out = []
    for dp, _dn, fn in os.walk(repo):
        if any(s in dp for s in _SKIP):
            continue
        out.extend(Path(dp) / f for f in fn if f.endswith(".java"))
    return out


def tool_repomap(repo: Path, arg: str) -> str:
    """Ranked map of the codebase: files (by cross-file reference count) ->
    their classes + method signatures. One call to orient instead of many."""
    repo = Path(repo).resolve()
    root = _safe(repo, arg.strip()) if arg.strip() else repo
    root = root or repo
    files = [f for f in _java_files(repo) if str(f).startswith(str(root))]
    if not files:
        return "(no java files under that path)"
    info, texts = {}, {}
    for f in files:
        try:
            t = f.read_text(errors="replace")
        except Exception:  # noqa: BLE001
            continue
        texts[f] = t
        classes = [m.group(2) for m in _DECL.finditer(t)]
        meths = []
        for m in _METH.finditer(t):
            params = re.sub(r"\s+", " ", m.group(2)).strip()
            sig = f"{m.group(1)}({params})"
            meths.append(sig[:70])
        info[f] = (classes, meths)
    blob = "\n".join(texts.values())
    score = {f: sum(len(re.findall(r"\b" + re.escape(c) + r"\b", blob))
                    for c in cl) for f, (cl, _) in info.items()}
    ranked = sorted(info, key=lambda f: -score.get(f, 0))
    lines, budget = [], 12000
    for i, f in enumerate(ranked):
        classes, meths = info[f]
        rel = str(f).replace(str(repo) + "/", "")
        block = [f"{rel}  (refs:{score.get(f, 0)})"]
        block += [f"  {c}" for c in classes[:2]]
        block += [f"    {s}" for s in meths[:12]]
        chunk = "\n".join(block)
        if budget - len(chunk) < 0:
            lines.append(f"... (+{len(ranked) - i} more files; narrow with repomap <subdir>)")
            break
        lines.append(chunk)
        budget -= len(chunk)
    return "\n".join(lines)


TOOLS = {"ls": tool_ls, "read_file": tool_read, "grep": tool_grep,
         "repomap": tool_repomap}

SYS = """You are an expert Java code reviewer reviewing a pull request. You have
tools to read the repository AT THE PR'S BASE COMMIT so you can understand the
surrounding code, conventions, and existing implementations before reviewing —
exactly what a great human reviewer does.

Each turn, think, then end your message with EXACTLY ONE action line:
  ACTION: repomap <dir>     # ranked map of files->classes->methods; START HERE to orient
  ACTION: ls <dir>
  ACTION: read_file <path>
  ACTION: grep <regex>
  ACTION: review
Start with `repomap` to orient (it's a ranked structural map of the codebase),
then use ls/read_file/grep to investigate (e.g. does this method already exist?
what does the touched API guarantee? what's the convention in neighboring files?).
When ready, use `ACTION: review` and then write the review AFTER that line:

SUMMARY:
<one short paragraph>
POINTS:
- [path/File.java:line] <specific, actionable point grounded in the real code>

Be specific and grounded in what you actually read. Budget: %d tool calls."""


def _inject_budget(policy: str, max_steps: int) -> str:
    """Insert the tool budget WITHOUT the fragile %-operator: a GEPA-mutated
    policy is free prose and will contain stray '%' (e.g. "100%") or drop the
    "%d" — using `policy % max_steps` then crashes the whole rollout (scores 0).
    Safe: replace the literal "%d" if present, else append a budget line."""
    if "%d" in policy:
        return policy.replace("%d", str(max_steps))
    return policy.rstrip() + f"\n\nBudget: {max_steps} tool calls."


def _parse_action(text: str):
    # last ACTION: line is the decision (reasoning may mention others)
    ms = list(re.finditer(r"(?im)^\s*ACTION:\s*(repomap|ls|read_file|grep|review)\b(.*)$", text))
    if not ms:
        return None, None, None
    m = ms[-1]
    tool, arg = m.group(1).lower(), m.group(2).strip()
    after = text[m.end():].strip()    # for review: the review body follows
    return tool, arg, after


def agent_review(repo_dir, pr_input, profile="qwen", max_steps=MAX_STEPS,
                 policy: str | None = None):
    """policy = the agent SYS prompt (the GEPA-optimizable genome). Must contain
    one '%d' for the tool budget. Defaults to the hand-written SYS."""
    repo = Path(repo_dir)
    llm = get_llm(profile)
    transcript = [{"role": "system", "content": _inject_budget(policy or SYS, max_steps)},
                  {"role": "user", "content":
                   "PULL REQUEST UNDER REVIEW:\n" + pr_input +
                   "\n\nInvestigate the repo as needed, then ACTION: review."}]
    trace = []
    for step in range(max_steps):
        out = llm.chat(transcript, max_tokens=None)          # think on; full answer
        tool, arg, after = _parse_action(out)
        if tool is None:        # no action -> treat whole thing as the review
            return final_review(out), trace + [("no-action", "")]
        if tool == "review":
            return final_review(after or out), trace + [("review", "")]
        obs = TOOLS[tool](repo, arg)
        trace.append((f"{tool} {arg}", obs[:160].replace("\n", " ")))
        transcript.append({"role": "assistant", "content": f"ACTION: {tool} {arg}"})
        transcript.append({"role": "user", "content": f"OBSERVATION:\n{obs}"})
    # ran out of steps -> ask for the review now
    transcript.append({"role": "user", "content": "Budget exhausted. Write the review now (SUMMARY/POINTS)."})
    return final_review(llm.chat(transcript, max_tokens=None)), trace


def diff_only_review(pr_input, profile="qwen"):
    llm = get_llm(profile)
    sysp = ("You are an expert Java code reviewer. Review this PR from the diff "
            "alone. Output SUMMARY: then POINTS: with file-anchored points.")
    return final_review(llm.complete(sysp, "PULL REQUEST:\n" + pr_input +
                                     "\n\nWrite the review."))


def run(repo_dir, repo, pr, profile="qwen"):
    inst = ds.build_instances()
    rv = next((x for v in inst.values() for x in v
               if x["repo"] == repo and str(x["pr"]) == str(pr)), None)
    if not rv:
        print(f"PR {repo}#{pr} not in excellent_reviews.json"); return
    pr_input, human = rv["input"], rv["reference_review"]
    print(f"=== {repo}#{pr} (reviewer {rv['reviewer']}) ===\n")
    print("--- DIFF-ONLY (Attempt 1) ---", flush=True)
    d = diff_only_review(pr_input, profile)
    ds_score, _ = mt.score_with_feedback(pr_input, d, human, profile)
    print(f"score={ds_score:.3f}\n", flush=True)
    print("--- AGENT + REPO (Attempt 2) ---", flush=True)
    a, trace = agent_review(repo_dir, pr_input, profile)
    for t, o in trace:
        print(f"  · {t}  ->  {o}")
    a_score, _ = mt.score_with_feedback(pr_input, a, human, profile)
    print(f"score={a_score:.3f}\n", flush=True)
    out = {"repo": repo, "pr": pr, "reviewer": rv["reviewer"], "human": human,
           "diff_only": {"review": d, "score": round(ds_score, 4)},
           "agent_repo": {"review": a, "score": round(a_score, 4),
                          "n_tool_calls": len(trace), "trace": trace}}
    Path("results").mkdir(exist_ok=True)
    Path(f"results/agent_poc_{repo.replace('/','_')}_{pr}.json").write_text(json.dumps(out, indent=2))
    print(f"DIFF-ONLY {ds_score:.3f}  vs  AGENT+REPO {a_score:.3f}  "
          f"(Δ {a_score-ds_score:+.3f}, {len(trace)} tool calls)")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]),
        sys.argv[4] if len(sys.argv) > 4 else "qwen")
