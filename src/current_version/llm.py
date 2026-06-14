"""v8 LLM layer — ported from the verified oh_review helpers (P8 + P14).

Provides the streaming-safe LLM the harness uses, the config/env wiring that keeps
the real endpoint URL out of the committed config, and the final-answer coercion
helpers. Behaviour is identical to v7; only ROOT (now 3 levels up from src/v8/)
and the module home changed.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

import yaml  # noqa: E402
from llm_client import final_review  # noqa: E402,F401  (reuse final-answer extraction)

# src/v8/llm.py -> parents[2] = current_attempt (where config.yaml + .env live)
ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())


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

from openhands.sdk import LLM  # noqa: E402

# --- request profiler: dump EXACTLY what is sent to vLLM (PROFILE_LOG set) -----------------
# A litellm pre-API hook sees the final request body (complete_input_dict): tools, stream,
# tool_choice, messages — so we can confirm whether OpenHands actually sends `tools`.
try:
    import litellm as _litellm
    from litellm.integrations.custom_logger import CustomLogger as _CustomLogger

    class _ProfileLogger(_CustomLogger):
        def log_pre_api_call(self, model, messages, kwargs):  # noqa: ARG002
            path = os.environ.get("PROFILE_LOG")
            if not path:
                return
            try:
                op = kwargs.get("optional_params", {}) or {}
                body = (kwargs.get("additional_args", {}) or {}).get("complete_input_dict", {}) or {}
                tools = body.get("tools") or op.get("tools") or []
                with open(path, "a") as f:
                    f.write(f"\n=== PRE-API model={model} stream={body.get('stream', op.get('stream'))} "
                            f"tool_choice={body.get('tool_choice', op.get('tool_choice'))} "
                            f"n_tools={len(tools)} n_msgs={len(messages or [])} ===\n")
                    if tools:
                        f.write("tools: " + ", ".join(
                            (t.get('function', {}) or {}).get('name', '?') for t in tools) + "\n")
                    f.write("body keys: " + ",".join(sorted(body.keys())) + "\n")
            except Exception:  # noqa: BLE001
                pass

    if os.environ.get("PROFILE_LOG"):
        _litellm.callbacks = [_ProfileLogger()]
except Exception:  # noqa: BLE001
    pass


_STREAM_BUF = []   # accumulates streamed deltas; flushed in ~400-char chunks (avoid per-token IO)


def _stream_tap(tok):
    """on_token callback: append streamed REASONING + content deltas to $REASONING_LOG LIVE.
    Reasoning tokens also stream, so this shows the model thinking DURING a long call instead
    of only after it returns (a giant generator call can run minutes — we must see inside it)."""
    path = os.environ.get("REASONING_LOG")
    if not path:
        return
    try:
        if isinstance(tok, str):
            piece = tok
        else:
            d = tok.choices[0].delta
            piece = (getattr(d, "reasoning_content", None) or "") + (getattr(d, "content", None) or "")
        if piece:
            _STREAM_BUF.append(piece)
            if sum(len(x) for x in _STREAM_BUF) >= 400:
                with open(path, "a") as f:
                    f.write("".join(_STREAM_BUF))
                _STREAM_BUF.clear()
    except Exception:  # noqa: BLE001
        pass


def _log_turn(usage_id, resp):
    """Turn end: flush any buffered stream, then record the tool calls (they don't stream as
    readable text — this is where a malformed name like `add_sicion` would show) + a separator."""
    path = os.environ.get("REASONING_LOG")
    if not path:
        return
    if _STREAM_BUF:
        try:
            with open(path, "a") as f:
                f.write("".join(_STREAM_BUF))
        except Exception:  # noqa: BLE001
            pass
        _STREAM_BUF.clear()
    try:
        msg = resp.choices[0].message
        tcs = getattr(msg, "tool_calls", None) or []
        with open(path, "a") as f:
            for t in tcs:
                fn = getattr(getattr(t, "function", None), "name", None)
                args = getattr(getattr(t, "function", None), "arguments", None)
                f.write(f"\n[tool_call] {fn}({str(args)[:600]})")
            f.write(f"\n===== end turn [{usage_id}] =====\n")
    except Exception:  # noqa: BLE001
        pass


class StreamingLLM(LLM):
    """stream=True turns httpx's read-timeout into a byte-gap heartbeat (P8/P14). OpenHands
    raises if stream=True and on_token is None; the agent loop passes on_token=None EXPLICITLY
    and the condenser passes it ABSENT, so inject our live-streaming tap for both (sync +
    async). The tap streams reasoning+content to $REASONING_LOG; _log_turn adds tool calls."""

    def completion(self, *a, **kw):
        if kw.get("on_token") is None:
            kw["on_token"] = _stream_tap
        resp = super().completion(*a, **kw)
        _log_turn(self.usage_id, resp)
        return resp

    async def acompletion(self, *a, **kw):
        if kw.get("on_token") is None:
            kw["on_token"] = _stream_tap
        resp = await super().acompletion(*a, **kw)
        _log_turn(self.usage_id, resp)
        return resp


def _llm(profile: str = "qwen"):
    c = CFG[profile]
    model = f"hosted_vllm/{c['model']}"
    # CRITICAL: litellm's registry doesn't know this custom vLLM model supports function
    # calling, so `supports_function_calling` returns False and OpenHands silently falls back
    # to PROMPT-BASED tool parsing (it looks for the tool call in `content`). With thinking
    # correctly separated the content is empty, so that path finds nothing -> the agent never
    # acts (it ruminates). The endpoint DOES do native tool calls (verified by direct curl),
    # so register the model as function-calling-capable and pin native_tool_calling on.
    try:
        import litellm
        info = {"litellm_provider": "hosted_vllm", "mode": "chat", "supports_function_calling": True}
        litellm.register_model({model: info, c["model"]: info})
    except Exception:  # noqa: BLE001
        pass
    return StreamingLLM(
        usage_id="oh_review",
        model=model,
        base_url=c["base_url"],
        api_key=os.environ.get(c.get("api_key_env", "QWEN_API_KEY"), "x"),
        temperature=c.get("temperature", 0.7),
        max_message_chars=300000,
        num_retries=10,
        retry_max_wait=120,
        native_tool_calling=True,   # use the OpenAI tools param + parse message.tool_calls
        # With stream=True the timeout is a byte-gap heartbeat: abort a request that
        # has gone silent for this long (vllm under concurrent load accepts the call
        # then stops streaming) so num_retries can re-issue it instead of hanging forever.
        timeout=c.get("request_timeout_s", 180),
        # stream toggle (OH_STREAM=0 to disable). stream=True was added for the Caddy idle-close
        # on long generations, but it appears to drop tool_calls in OpenHands' aggregation; with
        # native tools working, turns are short (think->call->return) so non-stream may be fine.
        stream=os.environ.get("OH_STREAM", "1") == "1",
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
    """Qwen emits reasoning inline; a lone '</think>' precedes the answer."""
    return s.rsplit("</think>", 1)[-1] if s and "</think>" in s else (s or "")
