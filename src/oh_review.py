"""Attempt 3 harness — OpenHands-SDK rollout for Java review.

Drop-in replacement for agent_review.agent_review(repo_dir, pr_input, profile,
max_steps, policy) -> (review, trace) so GEPA can swap harnesses with minimal
change. Runs the V1 OpenHands Software Agent SDK IN-PROCESS (no Docker) against
the repo checked out at the PR base commit, pointed at our thinking-Qwen endpoint.

MUST run under venv-oh (python>=3.12, has openhands-sdk + our deps).

  ./venv-oh/bin/python src/oh_review.py <repo_dir> <repo> <pr>   # smoke
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

sys.path.insert(0, os.path.dirname(__file__))
import yaml  # noqa: E402
from llm_client import final_review  # noqa: E402  (reuse final-answer extraction)

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
MAX_OH_STEPS = 40


def _load_env():
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _apply_endpoint_env():   # keep private endpoint URLs out of the committed config
    for _p, _c in CFG.items():
        if isinstance(_c, dict) and _c.get("base_url"):
            _ov = os.environ.get(f"{_p.upper()}_BASE_URL")
            if _ov:
                _c["base_url"] = _ov


_apply_endpoint_env()

from openhands.sdk import LLM, Agent, Conversation  # noqa: E402
from openhands.sdk.event import MessageEvent, ActionEvent  # noqa: E402
from openhands.tools.preset.default import get_default_tools  # noqa: E402

# --- enable STREAMING so the read-timeout measures byte-gaps, not whole-answer ---
# Non-streaming withholds every byte until the full answer is computed, so httpx's
# 300s read timeout collapses to "time to compute the entire response" and
# guillotines healthy long generations (64k ctx + thinking on a busy GPU) → retry
# loop → empty review → score 0.0. With streaming, tokens flow as a liveness
# heartbeat. But OpenHands raises ValueError if stream=True and on_token is None,
# and TWO call sites in OUR setup hit that with the SAME shared stream=True llm:
#   1. the agent loop  → completion(..., on_token=on_token)  with on_token *=None*
#      (key PRESENT, value None) — so `setdefault` would NOT fix it; need `is None`.
#   2. the condenser   → completion(messages=...)            with on_token absent.
# A scoped subclass that injects a no-op for BOTH shapes (sync + async acompletion,
# which the condenser also uses) is cleaner than monkeypatching LLM globally.
_NOOP_TOKEN = lambda _chunk: None  # noqa: E731  TokenCallbackType = Callable[[chunk],None]


class StreamingLLM(LLM):
    def completion(self, *a, **kw):
        if kw.get("on_token") is None:        # absent OR explicit None
            kw["on_token"] = _NOOP_TOKEN
        return super().completion(*a, **kw)

    async def acompletion(self, *a, **kw):
        if kw.get("on_token") is None:
            kw["on_token"] = _NOOP_TOKEN
        return await super().acompletion(*a, **kw)


# default policy (the GEPA genome when none supplied). OpenHands-flavoured tools.
OH_SYS = """You are an expert Java code reviewer reviewing a pull request. You have
READ-ONLY access to the repository at the PR's base commit (grep, glob, a file
viewer, a terminal for read commands). Investigate the surrounding code,
conventions, and existing implementations — exactly what a great human reviewer
does — then write the review. DO NOT edit, create, or delete any files.

When ready, output the review in EXACTLY this format and then stop:
SUMMARY:
<one short paragraph>
POINTS:
- [path/File.java:line] <specific, actionable point grounded in the real code>
"""


def _llm(profile: str = "qwen"):
    c = CFG[profile]
    return StreamingLLM(
        usage_id="oh_review",
        model=f"hosted_vllm/{c['model']}",
        base_url=c["base_url"],
        api_key=os.environ.get(c.get("api_key_env", "QWEN_API_KEY"), "x"),
        temperature=c.get("temperature", 0.7),
        # raise from the 30k default so the first user message (PR + full changed
        # files, up to ~64k tokens / ~240k chars) isn't silently truncated; also
        # lets full file-read observations through.
        max_message_chars=300000,
        # SHARED endpoint is heavily contended → dropped sockets / busy spells are
        # frequent. Ride them out instead of erroring a rollout to score 0.0. NOT a
        # cap on the agent (it makes unlimited calls, thinks unbounded) — only
        # transport resilience. Keep timeout at the 300s default; do NOT lower it,
        # a legit 64k-context generation can run long on a busy GPU.
        num_retries=10,
        retry_max_wait=120,
        # stream tokens → byte-flow is a liveness signal, so the 300s read timeout
        # no longer guillotines slow-but-alive generations (the 0.0 cause).
        stream=True,
        # cap OUTPUT generation at 128k tokens. Sized for the input: reviewing a 64k
        # changed-files context with thinking ON can legitimately need a long
        # chain-of-thought + review, so keep generous headroom (never clip real
        # reasoning). Still bounds the degenerate spiral that otherwise decodes to the
        # ~198k ceiling (~30 min → 0.0): 128k tok ≈ ~15 min worst case. Output-only —
        # does NOT shrink input; 64k in + 128k out = 192k < 262k max-model-len.
        max_output_tokens=131072,
        litellm_extra_body={"chat_template_kwargs":
                            {"enable_thinking": c.get("enable_thinking", True)}},
    )


def _to_text(x) -> str:
    """Coerce OpenHands content (str | list[str|block] | dict | obj) to text."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        parts = []
        for e in x:
            if isinstance(e, str):
                parts.append(e)
            elif isinstance(e, dict):
                parts.append(e.get("text") or e.get("content") or "")
            else:
                parts.append(getattr(e, "text", "") or "")
        return "\n".join(p for p in parts if p)
    if isinstance(x, dict):
        return x.get("text") or x.get("message") or x.get("content") or ""
    return getattr(x, "text", "") or str(x)


def _post_think(s: str) -> str:
    """Qwen emits reasoning inline; a lone '</think>' (no opening tag) precedes the
    answer. strip_think only handles PAIRED tags, so split on the last '</think>'."""
    return s.rsplit("</think>", 1)[-1] if s and "</think>" in s else (s or "")


def _action_label(a) -> str:
    name = getattr(a, "tool_name", type(a).__name__)
    arg = ""
    try:
        d = a.model_dump()
        for k in ("command", "action", "pattern", "path", "arguments", "query"):
            if d.get(k):
                arg = str(d[k]); break
    except Exception:  # noqa: BLE001
        pass
    return f"{name} {arg}".strip()[:120]


def oh_review(repo_dir, pr_input, profile="qwen", max_steps=MAX_OH_STEPS, policy=None):
    """Returns (review_text, trace) where trace = [(\"tool arg\", \"\"), ...] +
    a final ("review","") if it self-terminated (mirrors agent_review's trace)."""
    llm = _llm(profile)
    tools = get_default_tools(enable_browser=False)
    agent = Agent(llm=llm, tools=tools, system_prompt=(policy or OH_SYS))

    state = {"n": 0, "conv": None, "capped": False}

    def _cap_cb(ev):
        if isinstance(ev, ActionEvent):
            state["n"] += 1
            if state["n"] >= max_steps and state["conv"] is not None:
                state["capped"] = True
                try:
                    state["conv"].pause()
                except Exception:  # noqa: BLE001
                    pass

    conv = Conversation(agent=agent, workspace=str(repo_dir), callbacks=[_cap_cb])
    state["conv"] = conv
    conv.send_message("PULL REQUEST UNDER REVIEW:\n" + pr_input +
                      "\n\nInvestigate the repo as needed, then output the review.")
    conv.run()

    def _extract():
        ev = conv.state.events
        r = ""
        for a in reversed([e for e in ev if isinstance(e, ActionEvent)]):
            if getattr(a, "tool_name", None) == "finish":
                try:
                    d = a.model_dump()
                    r = _to_text(d.get("message") or d.get("thought"))
                except Exception:  # noqa: BLE001
                    r = ""
                if r.strip():
                    return r
        amsgs = [e for e in ev if isinstance(e, MessageEvent)
                 and getattr(e, "source", None) == "agent"]
        if amsgs:
            try:
                return _to_text([getattr(c, "text", "")
                                 for c in amsgs[-1].llm_message.content])
            except Exception:  # noqa: BLE001
                return str(amsgs[-1])
        return r

    raw = _extract()
    # forced finish only if we truly have nothing usable (no markers AND short)
    has_review = ("SUMMARY:" in raw) or ("POINTS:" in raw) or len(_post_think(raw)) > 200
    if not has_review:
        state["n"] = 0
        try:
            conv.send_message(
                "Stop investigating — do NOT call any more tools. Output the final "
                "code review NOW in EXACTLY this format:\nSUMMARY:\n<one paragraph>\n"
                "POINTS:\n- [path/File.java:line] <specific point>")
            conv.run()
            raw = _extract() or raw
        except Exception:  # noqa: BLE001
            pass
    if os.environ.get("OH_DEBUG"):
        print(">>> RAW(last400):", repr(raw[-400:]), flush=True)
    review = final_review(_post_think(raw))

    ev = conv.state.events
    trace = [(_action_label(a), "") for a in ev if isinstance(a, ActionEvent)]
    if not state["capped"]:
        trace.append(("review", ""))     # self-terminated
    return review, trace


def run(repo_dir, repo, pr, profile="qwen"):
    import dataset as ds
    import metric as mt
    inst = ds.build_instances()
    rv = next((x for v in inst.values() for x in v
               if x["repo"] == repo and str(x["pr"]) == str(pr)), None)
    if not rv:
        print(f"{repo}#{pr} not found"); return
    print(f"=== OpenHands harness: {repo}#{pr} ({rv['reviewer']}) ===", flush=True)
    review, trace = oh_review(repo_dir, rv["input"], profile)
    score, _ = mt.score_with_feedback(rv["input"], review, rv["reference_review"], profile)
    print("TOOLS:", [t for t, _ in trace])
    print("REVIEW:\n", review[:1200])
    print(f"\nSCORE vs human = {score:.3f}  ({len(trace)} actions)")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]),
        sys.argv[4] if len(sys.argv) > 4 else "qwen")
