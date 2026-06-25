import sys; sys.path.insert(0, "src")
from llm_client import get_llm
SYS = ("You are a senior Java and Gson maintainer. Reason carefully about the CORRECT behavior and the "
       "minimal fix for a bug. Weigh the serialization round-trip contract and the java.util.Locale "
       "specification. Do NOT just make a unit test pass - determine what the code SHOULD do. "
       "Give your reasoning, then the concrete fix.")
USR = r'''Gson's Locale TypeAdapter:
  WRITE: out.value(value == null ? null : value.toString());
  READ: split the string on "_" into language/country/variant (each initialized to null), then
        if (country == null && variant == null) return new Locale(language);
        else if (variant == null)               return new Locale(language, country);
        else                                    return new Locale(language, country, variant);

For input "" (empty JSON string) the tokenizer produces no tokens, so language stays null and
new Locale(null) throws NullPointerException.

Question: what SHOULD gson.fromJson("\"\"", Locale.class) return, and what is the minimal correct fix?
Reason it through first, then state the fix.'''
print(get_llm("qwen").complete(SYS, USR, temperature=0.0))
