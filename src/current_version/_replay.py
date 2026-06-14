"""Diagnostic: replay the generator's EXACT first call (real GENERATOR_SYS + real PR context
+ the add_suspicion tool) as a single direct litellm call, to see whether the model emits a
tool call or ruminates on the real task. Varies reasoning_effort. Not part of the harness."""
import os, sys, time, json
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml, litellm
import current_version.suspicion as S
from current_version import harness

repo, pr = sys.argv[1], int(sys.argv[2])
d, pi, tag = S._setup(repo, pr)
files = harness._changed_files_content(d, pi)
ctx = pi + (("\n\n=== FULL CONTENT OF THE CHANGED FILES (base commit) ===\n" + files) if files else "")
print(f"context chars: {len(ctx)}")

c = yaml.safe_load(open("config.yaml"))["qwen"]
model = f"hosted_vllm/{c['model']}"; base = os.environ["QWEN_BASE_URL"]; key = os.environ["QWEN_API_KEY"]
msgs = [{"role": "system", "content": S.GENERATOR_SYS},
        {"role": "user", "content": "PULL REQUEST:\n" + ctx +
         "\n\nRaise the suspicions now — call add_suspicion once for each."}]
tool = [{"type": "function", "function": {"name": "add_suspicion",
        "description": "Record one suspicion to fact-check later.",
        "parameters": {"type": "object", "properties": {
            "claim": {"type": "string"}, "location": {"type": "string"},
            "severity": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["claim", "location", "severity", "confidence"]}}}]

for tb in [1024, 4096]:
    t0 = time.time()
    r = litellm.completion(model=model, api_base=base, api_key=key, messages=msgs, tools=tool,
                           tool_choice="auto", max_tokens=14000, temperature=0,
                           extra_body={"chat_template_kwargs": {"enable_thinking": True},
                                       "thinking_token_budget": tb})
    m = r.choices[0].message
    print(f"thinking_token_budget={tb} t={time.time()-t0:.0f}s finish={r.choices[0].finish_reason} "
          f"tool_calls={len(m.tool_calls or [])} reasoning_chars={len(getattr(m,'reasoning_content',None) or '')} "
          f"content={repr((m.content or '')[:60])}")
