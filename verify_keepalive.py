"""Prove TCP keepalive is actually set on the endpoint socket, on BOTH client paths.
Capture every setsockopt() call during a real request; assert SO_KEEPALIVE was enabled."""
import sys, socket; sys.path.insert(0, "src")

_CAPTURED = []
_orig = socket.socket.setsockopt
def _spy(self, level, optname, value, *a):
    _CAPTURED.append((level, optname, value))
    return _orig(self, level, optname, value, *a)
socket.socket.setsockopt = _spy

def _had_keepalive():
    on = any(l == socket.SOL_SOCKET and o == socket.SO_KEEPALIVE and v == 1 for l, o, v in _CAPTURED)
    idle = [v for l, o, v in _CAPTURED if hasattr(socket, "TCP_KEEPIDLE") and o == socket.TCP_KEEPIDLE]
    return on, idle

# ---- Path 1: single-call OpenAI SDK path (llm_client) ----
_CAPTURED.clear()
from llm_client import get_llm
out = get_llm("qwen").complete("", "Reply with the single word: ok", max_tokens=8)
on, idle = _had_keepalive()
print(f"[single-call]  SO_KEEPALIVE set: {on}  TCP_KEEPIDLE: {idle}  (reply: {out[:30]!r})")

# ---- Path 2: harness path (litellm via our injected client_session) ----
_CAPTURED.clear()
from current_version import llm as L
L._install_keepalive_clients()
import litellm
c = L.CFG["qwen"]
r = litellm.completion(model=f"hosted_vllm/{c['model']}", base_url=c["base_url"],
                       api_key=__import__("os").environ.get("QWEN_API_KEY", "x"),
                       messages=[{"role": "user", "content": "Reply with the single word: ok"}],
                       max_tokens=8, drop_params=False)
on2, idle2 = _had_keepalive()
print(f"[harness/litellm]  SO_KEEPALIVE set: {on2}  TCP_KEEPIDLE: {idle2}  (call ok: {r is not None})")
print("[harness] client_session is keepalive client:", litellm.client_session is not None,
      "| aclient_session set:", litellm.aclient_session is not None)

print("RESULT:", "PASS" if (on and on2) else "FAIL")
