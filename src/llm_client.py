"""OpenAI-compatible chat client for the Qwen vLLM endpoint (and any
OpenAI-format target, e.g. a future Claude proxy).

Kept model-agnostic: base_url / model / api_key come from config + .env, so the
GEPA stage can be re-pointed at another model without code changes.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import yaml
from openai import OpenAI

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_SUMMARY = re.compile(r"(?:^|\n)\s*SUMMARY\s*:", re.I)
_POINTS = re.compile(r"(?:^|\n)\s*POINTS\s*:", re.I)


def strip_think(text: str) -> str:
    """Remove Qwen reasoning blocks and leading whitespace."""
    return _THINK.sub("", text or "").strip()


def final_review(text: str) -> str:
    """Extract the model's FINAL review, discarding the thinking process.

    This endpoint emits reasoning as plain prose in `content` (no <think> tags,
    no reasoning_content), with the actual review at the end. Thinking is just
    context-filling and may contain self-corrected wrong turns -> only the final
    answer should be compared to the human. We take the LAST SUMMARY:/POINTS:
    block (the answer always follows the reasoning)."""
    t = strip_think(text)
    ms = list(_SUMMARY.finditer(t)) or list(_POINTS.finditer(t))
    return t[ms[-1].start():].strip() if ms else t


def last_json(text: str) -> str | None:
    """The LAST balanced {...} in the text (the answer after any reasoning)."""
    end = (text or "").rfind("}")
    if end == -1:
        return None
    start = text.rfind("{", 0, end)
    while start != -1:
        cand = text[start:end + 1]
        try:
            import json as _j
            _j.loads(cand)
            return cand
        except Exception:  # noqa: BLE001
            start = text.rfind("{", 0, start)
    return None

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
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


class LLM:
    def __init__(self, profile: str = "qwen"):
        c = CFG[profile]
        self.model = c["model"]
        self.max_tokens = c.get("max_tokens", 1500)
        self.temperature = c.get("temperature", 0.2)
        self.timeout = c.get("request_timeout_s", 120)
        self.enable_thinking = c.get("enable_thinking", False)
        self.sem = threading.Semaphore(c.get("max_concurrency", 4))
        key_env = c.get("api_key_env", "QWEN_API_KEY")
        self.client = OpenAI(
            base_url=c["base_url"],
            api_key=os.environ.get(key_env, "x"),
            timeout=self.timeout,
        )
        self.calls = 0

    def chat(self, messages, temperature=None, max_tokens=None, retries=4,
             think=None):
        last = None
        use_think = self.enable_thinking if think is None else think
        extra = {"chat_template_kwargs": {"enable_thinking": use_think}}
        for attempt in range(retries):
            try:
                with self.sem:
                    # stream=True so a long generation keeps bytes flowing — a proxy/gateway
                    # in front of vLLM closes an idle single-shot connection after its read
                    # timeout (~60-100s), which is what killed long synthesizer/generator calls.
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature if temperature is None else temperature,
                        max_tokens=max_tokens or self.max_tokens,
                        extra_body=extra,
                        stream=True,
                        stream_options={"include_usage": True},
                    )
                    content, u = "", None
                    for chunk in stream:
                        if chunk.usage is not None:
                            u = chunk.usage
                        if chunk.choices and chunk.choices[0].delta.content:
                            content += chunk.choices[0].delta.content
                self.calls += 1
                try:
                    if u:
                        TOKENS["prompt"] += int(getattr(u, "prompt_tokens", 0) or 0)
                        TOKENS["completion"] += int(getattr(u, "completion_tokens", 0) or 0)
                    LAST["messages"] = messages
                    LAST["raw"] = content
                    LAST["usage"] = ({"prompt_tokens": getattr(u, "prompt_tokens", None),
                                      "completion_tokens": getattr(u, "completion_tokens", None)}
                                     if u else None)
                except Exception:  # noqa: BLE001
                    pass
                return strip_think(content)
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(min(20, 2 ** attempt + 1))
        raise RuntimeError(f"LLM call failed after {retries}: {last}")

    def complete(self, system: str, user: str, **kw) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        return self.chat(msgs, **kw)


# module-level token accounting (OpenAI-SDK path: mr / mr_code single calls)
TOKENS = {"prompt": 0, "completion": 0}
# last raw exchange (messages sent + raw completion WITH thinking) for trace-saving
LAST = {"messages": None, "raw": None, "usage": None}

# convenience singletons (lazy)
_cache: dict[str, LLM] = {}


def get_llm(profile: str = "qwen") -> LLM:
    if profile not in _cache:
        _cache[profile] = LLM(profile)
    return _cache[profile]


if __name__ == "__main__":
    llm = get_llm("qwen")
    print(llm.complete("You are terse.", "Say 'pipeline online' and nothing else."))
