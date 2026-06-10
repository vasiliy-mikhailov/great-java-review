"""Context-ladder smoke for the Qwen endpoint via the OpenHands LLM path.

For each prompt size (hi, 1k, 16k, 32k, 64k tokens) call OpenHands' LLM.completion
in BOTH streaming and non-streaming mode, single attempt (num_retries=0), with a
per-call SIGALRM watchdog so a stall is reported instead of hanging forever.
Records time-to-first-token (streaming), total time, output length, and status.

  ./venv-oh/bin/python -u src/ladder_smoke.py
"""
from __future__ import annotations
import os, sys, time, signal
sys.path.insert(0, os.path.dirname(__file__))
import oh_review                      # noqa: E402  applies streaming-noop monkeypatch
from oh_review import CFG, _load_env  # noqa: E402
_load_env()
from openhands.sdk import LLM, Message, TextContent  # noqa: E402

PER_CALL = 240   # watchdog seconds; >this => report STALL and move on
SIZES = [0, 1000, 16000, 32000, 64000]


def make_llm(stream: bool):
    c = CFG["qwen"]
    return LLM(
        usage_id="ladder", model=f"hosted_vllm/{c['model']}", base_url=c["base_url"],
        api_key=os.environ.get(c.get("api_key_env", "QWEN_API_KEY"), "x"),
        temperature=0.7, max_message_chars=300000, num_retries=0, stream=stream,
        litellm_extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )


def prompt_of(ntok: int) -> str:
    if ntok == 0:
        return "hi"
    sent = "In Java, the volatile keyword affects visibility but not atomicity. "
    s = (sent * ((ntok // 12) + 2))[: ntok * 4]   # ~4 chars/token
    return s + "\n\nReply with ONE short sentence: what did this text discuss?"


def text_of(resp):
    m = resp.message
    parts = [getattr(c, "text", "") for c in (m.content or [])]
    rc = getattr(m, "reasoning_content", "") or ""
    return rc, "".join(p for p in parts if p)


class _Watchdog(Exception):
    pass


def _alarm(_s, _f):
    raise _Watchdog()


def run_one(llm, ntok, stream):
    first = {"t": None}
    t0 = time.time()

    def on_token(_chunk):
        if first["t"] is None:
            first["t"] = time.time()

    msg = Message(role="user", content=[TextContent(text=prompt_of(ntok))])
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(PER_CALL)
    try:
        kw = {"messages": [msg], "tools": []}
        if stream:
            kw["on_token"] = on_token
        resp = llm.completion(**kw)
        dt = time.time() - t0
        rc, out = text_of(resp)
        ttft = (first["t"] - t0) if first["t"] else None
        ttft_s = f"{ttft:.1f}s" if ttft is not None else "-"
        return (f"OK   total={dt:6.1f}s  ttft={ttft_s:>7}  "
                f"think={len(rc):5d}c  answer={len(out):4d}c")
    except _Watchdog:
        ttft = (first["t"] - t0) if first["t"] else None
        return (f"STALL >{PER_CALL}s  (first_token="
                f"{f'{ttft:.1f}s' if ttft else 'NONE'})")
    except Exception as e:  # noqa: BLE001
        return f"ERR  {type(e).__name__}: {str(e)[:120]}  (after {time.time()-t0:.1f}s)"
    finally:
        signal.alarm(0)


def main():
    llm_s, llm_n = make_llm(True), make_llm(False)
    print(f"per-call watchdog={PER_CALL}s  num_retries=0  enable_thinking=True\n", flush=True)
    print(f"{'size':>6} | {'STREAMING':<55} | NON-STREAMING", flush=True)
    print("-" * 110, flush=True)
    for nt in SIZES:
        label = "hi" if nt == 0 else f"{nt//1000}k"
        s = run_one(llm_s, nt, True)
        print(f"{label:>6} | {s:<55} | ...", flush=True)
        n = run_one(llm_n, nt, False)
        print(f"{'':>6} | {'':<55} | {n}", flush=True)
        print("-" * 110, flush=True)


if __name__ == "__main__":
    main()
