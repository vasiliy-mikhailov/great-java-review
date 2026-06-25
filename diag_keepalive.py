import sys, os, socket; sys.path.insert(0, "src")
_CAP = []
_orig = socket.socket.setsockopt
socket.socket.setsockopt = lambda self, l, o, v, *a: (_CAP.append((l, o, v)), _orig(self, l, o, v, *a))[1]
def ka(): return any(l == socket.SOL_SOCKET and o == socket.SO_KEEPALIVE and v == 1 for l, o, v in _CAP)

from current_version import llm as L
L._install_keepalive_clients()
import litellm
from litellm.llms.openai.common_utils import BaseOpenAILLM
_g = BaseOpenAILLM._get_sync_http_client
def spy():
    r = _g()
    print("  _get_sync_http_client called; returns our session:", r is litellm.client_session)
    return r
BaseOpenAILLM._get_sync_http_client = staticmethod(spy)

# flush any pre-cached openai client so it rebuilds with our client_session
try:
    litellm.in_memory_llm_clients_cache.flush_cache(); print("flushed client cache")
except Exception as e:
    print("flush failed:", e)

c = L.CFG["qwen"]
_CAP.clear()
litellm.completion(model=f"hosted_vllm/{c['model']}", base_url=c["base_url"],
                   api_key=os.environ.get("QWEN_API_KEY", "x"),
                   messages=[{"role": "user", "content": "say ok"}], max_tokens=8, drop_params=False)
print("after flushed call -> SO_KEEPALIVE fired:", ka())
