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

_NOOP_TOKEN = lambda _chunk: None  # noqa: E731


class StreamingLLM(LLM):
    """stream=True turns httpx's read-timeout into a byte-gap heartbeat (P8/P14). But
    OpenHands raises if stream=True and on_token is None, and two call sites hit the
    shared llm: the agent loop passes on_token=None EXPLICITLY (so `setdefault` would
    not fix it — need `is None`), the condenser passes it ABSENT. Inject a no-op for
    both, sync + async (the condenser uses acompletion)."""

    def completion(self, *a, **kw):
        if kw.get("on_token") is None:
            kw["on_token"] = _NOOP_TOKEN
        return super().completion(*a, **kw)

    async def acompletion(self, *a, **kw):
        if kw.get("on_token") is None:
            kw["on_token"] = _NOOP_TOKEN
        return await super().acompletion(*a, **kw)


def _llm(profile: str = "qwen"):
    c = CFG[profile]
    return StreamingLLM(
        usage_id="oh_review",
        model=f"hosted_vllm/{c['model']}",
        base_url=c["base_url"],
        api_key=os.environ.get(c.get("api_key_env", "QWEN_API_KEY"), "x"),
        temperature=c.get("temperature", 0.7),
        max_message_chars=300000,
        num_retries=10,
        retry_max_wait=120,
        stream=True,
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
