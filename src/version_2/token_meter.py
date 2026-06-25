"""Uniform token accounting across BOTH model paths:
  - OpenAI-SDK path (mr / mr_code) -> llm_client.TOKENS (filled in LLM.chat)
  - litellm path (mr_code_tools: OpenHands orchestrator + subagents + condenser) ->
    a global litellm CustomLogger that sums usage from EVERY completion.

Usage:
  import token_meter as tm; tm.install()
  p0, c0 = tm.total(); ...run a condition...; p1, c1 = tm.total()
  prompt_tokens = p1 - p0; completion_tokens = c1 - c0
"""
from __future__ import annotations
import threading

_lock = threading.Lock()
_lite = {"prompt": 0, "completion": 0}


def _add(u):
    if not u:
        return
    def g(k):
        v = getattr(u, k, None)
        if v is None and isinstance(u, dict):
            v = u.get(k)
        return int(v or 0)
    with _lock:
        _lite["prompt"] += g("prompt_tokens")
        _lite["completion"] += g("completion_tokens")


_installed = False


def install():
    global _installed
    if _installed:
        return
    try:
        import litellm
        from litellm.integrations.custom_logger import CustomLogger

        class _Meter(CustomLogger):
            def log_success_event(self, kwargs, response_obj, start_time, end_time):
                try:
                    u = getattr(response_obj, "usage", None)
                    if u is None and isinstance(response_obj, dict):
                        u = response_obj.get("usage")
                    _add(u)
                except Exception:  # noqa: BLE001
                    pass

            async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
                try:
                    u = getattr(response_obj, "usage", None)
                    if u is None and isinstance(response_obj, dict):
                        u = response_obj.get("usage")
                    _add(u)
                except Exception:  # noqa: BLE001
                    pass

        litellm.callbacks = (litellm.callbacks or []) + [_Meter()]
        # ensure streaming responses still report usage
        try:
            litellm.modify_params = True
        except Exception:  # noqa: BLE001
            pass
        _installed = True
    except Exception:  # noqa: BLE001
        _installed = True  # don't crash the run if litellm wiring changes


def total():
    """(prompt, completion) tokens summed across both paths since process start."""
    import llm_client as lc
    return (_lite["prompt"] + lc.TOKENS["prompt"],
            _lite["completion"] + lc.TOKENS["completion"])
