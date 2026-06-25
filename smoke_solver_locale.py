import sys, ast; sys.path.insert(0, "src")
from llm_client import get_llm

# Pull the ACTUAL deployed SOLVER_SYS (no heavy imports) via ast
mod = ast.parse(open("src/current_version/suspicion.py").read())
SOLVER_SYS = next(n.value.value for n in mod.body
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SOLVER_SYS")

# Hand the solver the WRONG-DIRECTION test (asserts a throw) + the bug.
USR = r'''BUG: Gson Locale TypeAdapter NPEs on empty string.
  com/google/gson/internal/bind/TypeAdapters.java, Locale adapter:
    WRITE: out.value(value == null ? null : value.toString());   // Locale.ROOT -> ""
    READ:  StringTokenizer on "_"; language/country/variant init null;
           return new Locale(language[, country[, variant]]);
  Input "" yields no tokens -> language stays null -> new Locale(null) -> NullPointerException.

THE FAILING TEST you must turn green (DefaultTypeAdaptersTest.java):
  @Test public void testLocaleEmptyStringThrows() {
    assertThrows(JsonParseException.class, () -> gson.fromJson("\"\"", Locale.class));
  }

This test currently fails (NPE, not JsonParseException). Produce the fix.'''

print(get_llm("qwen").complete(SOLVER_SYS, USR, temperature=0.0))
