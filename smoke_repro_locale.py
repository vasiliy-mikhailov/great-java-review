import sys, ast; sys.path.insert(0, "src")
from llm_client import get_llm

mod = ast.parse(open("src/current_version/suspicion.py").read())
REPRODUCER_SYS = next(n.value.value for n in mod.body
                      if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "REPRODUCER_SYS")

USR = r'''You have ALREADY read the code (no tools available now — answer directly from this source).

  // com/google/gson/internal/bind/TypeAdapters.java -- Locale adapter
  public void write(JsonWriter out, Locale value) { out.value(value == null ? null : value.toString()); }
  public Locale read(JsonReader in) {
    if (in.peek() == JsonToken.NULL) { in.nextNull(); return null; }
    String locale = in.nextString();
    StringTokenizer tokenizer = new StringTokenizer(locale, "_");
    String language = null, country = null, variant = null;
    if (tokenizer.hasMoreElements()) language = tokenizer.nextElement().toString();
    if (tokenizer.hasMoreElements()) country  = tokenizer.nextElement().toString();
    if (tokenizer.hasMoreElements()) variant  = tokenizer.nextElement().toString();
    if (country == null && variant == null) return new Locale(language);
    else if (variant == null)               return new Locale(language, country);
    else                                    return new Locale(language, country, variant);
  }

SUSPICION: input "" -> no tokens -> language stays null -> new Locale(null) -> NullPointerException.

State the exact assertion(s) for the regression @Test you would write, and explain WHY that is the
correct expected behaviour the bug violates. Be concrete and brief.'''

print(get_llm("qwen").complete(REPRODUCER_SYS, USR, temperature=0.0))
