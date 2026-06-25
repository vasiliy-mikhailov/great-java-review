"""Per-LLM-call logger via a litellm CustomLogger — captures EVERY call across the whole
delegation tree (orchestrator + each subagent sub-conversation + condenser), which the
orchestrator's event dump cannot reach. One JSONL line per call:

  {start, end, dur, model, prompt_tokens, completion_tokens, role, sys, nmsgs,
   thought (assistant text = the INTENT), tools [names+brief args]}

Classify who made the call by the `sys` fingerprint (ORCH_SYS / CODE_EXPLORER /
INVESTIGATOR / JUDGE / condenser). Enable with call_log.install(path).
"""
from __future__ import annotations
import json, threading

_lock = threading.Lock()
_installed = False
_PATH = None


def set_path(path):
    """Switch the JSONL target (so one installed logger can serve many PRs)."""
    global _PATH
    _PATH = path


def _txt(x):
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(_txt(i) for i in x)
    if isinstance(x, dict):
        return _txt(x.get("text") or x.get("content") or "")
    return str(x) if x is not None else ""


def _extract_msg(response_obj, kwargs):
    """Return (assistant_text, [tool {name,args}]) from a (possibly streaming) response."""
    msg = None
    try:
        msg = response_obj.choices[0].message
    except Exception:  # noqa: BLE001
        csr = kwargs.get("complete_streaming_response") if isinstance(kwargs, dict) else None
        if csr is not None:
            try:
                msg = csr.choices[0].message
            except Exception:  # noqa: BLE001
                msg = None
    if msg is None:
        return "", []
    text = _txt(getattr(msg, "content", "") or "")
    tools = []
    for tc in (getattr(msg, "tool_calls", None) or []):
        try:
            fn = tc.function
            tools.append({"name": getattr(fn, "name", None),
                          "args": (getattr(fn, "arguments", "") or "")[:200]})
        except Exception:  # noqa: BLE001
            pass
    return text, tools


def install(path=None):
    global _installed
    if path:
        set_path(path)
    if _installed:
        return
    try:
        import litellm
        from litellm.integrations.custom_logger import CustomLogger

        def _rec(kwargs, response_obj, start_time, end_time):
            try:
                msgs = kwargs.get("messages") if isinstance(kwargs, dict) else None
                sys = ""
                if msgs:
                    for m in msgs:
                        if (m.get("role") if isinstance(m, dict) else None) == "system":
                            sys = _txt(m.get("content"))[:120]
                            break
                u = getattr(response_obj, "usage", None)
                pt = int(getattr(u, "prompt_tokens", 0) or 0) if u else None
                ct = int(getattr(u, "completion_tokens", 0) or 0) if u else None
                thought, tools = _extract_msg(response_obj, kwargs)
                row = {
                    "start": start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
                    "end": end_time.isoformat() if hasattr(end_time, "isoformat") else str(end_time),
                    "dur": ((end_time - start_time).total_seconds()
                            if hasattr(end_time, "isoformat") else None),
                    "model": kwargs.get("model") if isinstance(kwargs, dict) else None,
                    "prompt_tokens": pt, "completion_tokens": ct,
                    "sys": sys, "nmsgs": len(msgs) if msgs else None,
                    "thought": thought[:4000], "tools": tools,
                }
                tgt = _PATH or path
                if tgt:
                    with _lock:
                        with open(tgt, "a") as f:
                            f.write(json.dumps(row, default=str) + "\n")
            except Exception:  # noqa: BLE001
                pass

        class _Log(CustomLogger):
            def log_success_event(self, kwargs, response_obj, start_time, end_time):
                _rec(kwargs, response_obj, start_time, end_time)

            async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
                _rec(kwargs, response_obj, start_time, end_time)

        litellm.callbacks = (litellm.callbacks or []) + [_Log()]
        _installed = True
    except Exception:  # noqa: BLE001
        _installed = True
