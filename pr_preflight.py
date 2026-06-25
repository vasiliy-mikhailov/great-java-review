#!/usr/bin/env python3
"""Pre-flight checks before opening an upstream PR (AGENTS.md P17, curation).

The SELECTION factor is the maintainer's conduct toward contributors, not their
AI stance. Guards (warnings only, never a hard block; the operator decides):

  maintainer  profile the active maintainer's recent public interactions and
              judge engage vs avoid. Ban-prone / shaming / "spam"-dismissing
              maintainers are reputation-negative to deal with: skip them. This
              is the gate. (needs `gh` + GH_TOKEN)
  tells       lint changed files + PR body for non-idiomatic residue: em-dash,
              anonymous inner class (use a lambda), narrating comments. This is
              PR quality, not concealment.
  format      which formatter the repo uses, so touched files read hand-written.
  policy      footnote only: surface any AI clause (informational) and CLA/DCO
              (you still must sign one to merge). Does NOT gate.

Exit 0 = clean, 2 = actionable warnings (avoid-maintainer or tells).

Usage:
  pr_preflight.py maintainer <repo_dir | owner/name>
  pr_preflight.py tells      <file ...>
  pr_preflight.py format     <repo_dir>
  pr_preflight.py policy     <repo_dir>
  pr_preflight.py all        <repo_dir> <changed_file ...>
"""
import sys, os, re, glob, json, subprocess

EM, EN = "—", "–"

# ---------- maintainer conduct (the gate) ----------
TOXIC = ["banned", "is now banned", "hereby banned", "will ban", "shame", " spam",
         "useless", "waste of", "don't ask", "do not ask", "don't argue", "i don't need",
         "do it, don't", "do it don't", "at face value", "bankrupt", "won't argue",
         "not interested", "go away", "late by", "ai slop", "stop asking", "don't suggest",
         "left with nothing", "don't keep asking"]
RESPECT = ["thank", "appreciate", "good catch", "kudos", "welcome", "lgtm", "merged",
           "could you", "would you", "please", "let's", "feel free", "happy to",
           "good point", "makes sense", "fair enough", "great work", "nice work",
           "good idea", "well done", "will look into"]

def _gh(endpoint):
    try:
        r = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None

def _slug(arg):
    if os.path.isdir(arg):
        r = subprocess.run(["git", "-C", arg, "remote", "get-url", "origin"],
                           capture_output=True, text=True)
        m = re.search(r"github\.com[:/]([^/]+/[^/.\s]+)", r.stdout)
        return m.group(1) if m else None
    return arg.strip("/")

def _maintainers(slug):
    from collections import Counter
    prs = _gh(f"repos/{slug}/pulls?state=closed&per_page=50") or []
    c = Counter(p["merged_by"]["login"] for p in prs
                if p.get("merged_by") and not p["merged_by"]["login"].endswith("[bot]"))
    logins = [l for l, _ in c.most_common(3)]
    if not logins:
        cs = _gh(f"repos/{slug}/contributors?per_page=5") or []
        logins = [c["login"] for c in cs if not c["login"].endswith("[bot]")][:2]
    return logins

def _profile(login):
    evs = _gh(f"users/{login}/events/public") or []
    msgs = []
    for e in evs:
        t, p = e.get("type"), e.get("payload", {})
        b = None
        if t == "IssueCommentEvent": b = p.get("comment", {}).get("body")
        elif t == "PullRequestReviewCommentEvent": b = p.get("comment", {}).get("body")
        elif t == "PullRequestReviewEvent": b = p.get("review", {}).get("body")
        if b: msgs.append(" ".join(b.split()))
    tox = resp = bans = 0
    ex_t, ex_r = [], []
    for m in msgs:
        ml = m.lower()
        if any(w in ml for w in TOXIC):
            tox += 1; ex_t.append(m[:150])
        if any(w in ml for w in RESPECT):
            resp += 1; ex_r.append(m[:150])
        if any(w in ml for w in ("banned", "hereby banned", "will ban", "is now banned")):
            bans += 1
    return dict(login=login, n=len(msgs), tox=tox, resp=resp, bans=bans, ex_t=ex_t[:2], ex_r=ex_r[:1])

def screen_maintainer(arg):
    slug = _slug(arg)
    if not slug:
        print("  [MAINTAINER] could not resolve repo slug"); return []
    mts = _maintainers(slug)
    if not mts:
        print("  [MAINTAINER] could not resolve maintainers (is `gh` authed / GH_TOKEN set?)"); return []
    avoid = []
    for login in mts:
        p = _profile(login)
        if p["n"] == 0:
            print(f"  [MAINTAINER:?] @{login}  no recent public comments to judge"); continue
        if p["bans"] >= 1 or p["tox"] > max(1, p["resp"]) * 1.5:
            v = "AVOID"
        elif p["resp"] >= p["tox"]:
            v = "ENGAGE"
        else:
            v = "CAUTION"
        if v == "AVOID":
            avoid.append(login)
        print(f"  [MAINTAINER:{v}] @{login}  respect={p['resp']} toxic={p['tox']} bans={p['bans']} (of {p['n']} recent comments)")
        for e in p["ex_t"]: print(f"      x {e}")
        for e in p["ex_r"]: print(f"      ok {e}")
    if avoid:
        print(f"  >> reputation-negative maintainer(s): {', '.join('@'+a for a in avoid)} — lean toward skipping this repo")
    return avoid

# ---------- tells lint (PR quality) ----------
ANON_CLASS = re.compile(r"\bnew\s+[A-Z][\w.]*\s*(?:<[^;\n]*?>)?\s*\(\s*\)\s*\{")
LLM_PROSE = [re.compile(p, re.I) for p in [
    r"it'?s worth noting", r"\bnot just\b.*\bbut\b", r"\bmoreover\b", r"\bfurthermore\b",
    r"\bin summary\b", r"\boverall,", r"\bdelve\b", r"\bseamless", r"\bunderscore", r"\bnavigat"]]

def lint_tells(paths):
    w, files = [], []
    for p in paths:
        if os.path.isdir(p):
            files += [f for f in glob.glob(os.path.join(p, "**", "*"), recursive=True)
                      if os.path.isfile(f) and f.endswith((".java", ".md", ".txt"))]
        elif os.path.isfile(p):
            files.append(p)
    for f in files:
        try: txt = open(f, errors="ignore").read()
        except OSError: continue
        is_java = f.endswith(".java")
        for i, ln in enumerate(txt.splitlines(), 1):
            if EM in ln or EN in ln:
                w.append(("EM-DASH", f, i, ln.strip()[:120]))
            if is_java and ANON_CLASS.search(ln):
                w.append(("ANON-CLASS", f, i, ln.strip()[:120]))
            if (not is_java) or ln.lstrip().startswith(("//", "*")):
                for pat in LLM_PROSE:
                    if pat.search(ln):
                        w.append(("LLM-PROSE", f, i, ln.strip()[:120])); break
    return w

# ---------- formatter detect ----------
def detect_format(repo):
    blob = ""
    for g in glob.glob(os.path.join(repo, "**", "build.gradle*"), recursive=True)[:30] + \
             glob.glob(os.path.join(repo, "**", "pom.xml"), recursive=True)[:30]:
        try: blob += open(g, errors="ignore").read()
        except OSError: pass
    low, out = blob.lower(), []
    if "spotless" in low: out.append("spotless -> ./gradlew spotlessApply  (or mvn spotless:apply)")
    if "google-java-format" in low or "googlejavaformat" in low: out.append("google-java-format in the build")
    if glob.glob(os.path.join(repo, "**", "checkstyle*.xml"), recursive=True) or "checkstyle" in low:
        out.append("checkstyle present -> match its rules (checkstyleMain / checkstyle:check)")
    if not out: out.append("no formatter config found -> google-java-format the touched files to normalize")
    return out

# ---------- policy (footnote only) ----------
AI_PAT = re.compile(r"\b(ai[- ]?generated|generated by ai|artificial intelligence|llm|chatgpt|"
                    r"copilot|ai[- ]?assisted|ai contribution|machine[- ]?generated|ai slop|"
                    r"generative ai|large language model|ai[- ]?tool)\b", re.I)
CLA_PAT = re.compile(r"\b(contributor license agreement|\bcla\b|\bdco\b|"
                     r"developer certificate of origin|signed-off-by|sign the cla|\bicla\b)\b", re.I)
POLICY_GLOBS = ["CONTRIBUTING*", ".github/CONTRIBUTING*", ".github/PULL_REQUEST_TEMPLATE*",
                ".github/pull_request_template*", "CODE_OF_CONDUCT*", "docs/CONTRIBUTING*"]

def screen_policy(repo):
    ai, cla = [], []
    seen = set()
    for g in POLICY_GLOBS:
        for f in glob.glob(os.path.join(repo, g)):
            if not os.path.isfile(f) or os.path.realpath(f) in seen: continue
            seen.add(os.path.realpath(f))
            rel = os.path.relpath(f, repo)
            for i, ln in enumerate(open(f, errors="ignore").read().splitlines(), 1):
                if AI_PAT.search(ln): ai.append((rel, i, ln.strip()[:140]))
                if CLA_PAT.search(ln): cla.append((rel, i, ln.strip()[:140]))
    if cla: print(f"  [POLICY] CLA/DCO required — sign it: {cla[0][0]}:{cla[0][1]}")
    if ai: print(f"  [POLICY] (footnote) AI clause present at {ai[0][0]}:{ai[0][1]} — informational, not a gate")
    if not cla and not ai: print("  [POLICY] no CLA/DCO or AI clause found")

def report(label, warns):
    if not warns: print(f"  [{label}] clean")
    for kind, f, i, ln in warns: print(f"  [{label}:{kind}] {f}:{i}  {ln}")

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    exit_warns = []
    if cmd in ("maintainer", "all"):
        avoid = screen_maintainer(args[0])
        exit_warns += avoid
    if cmd == "tells":
        w = lint_tells(args); report("TELLS", w); exit_warns += w
    if cmd == "all":
        paths = [f if os.path.isabs(f) else os.path.join(args[0], f) for f in args[1:]]
        w = lint_tells(paths); report("TELLS", w); exit_warns += w
    if cmd in ("format", "all"):
        for s in detect_format(args[0]): print("  [FORMAT]", s)
    if cmd in ("policy", "all"):
        screen_policy(args[0])
    sys.exit(2 if exit_warns else 0)

if __name__ == "__main__":
    main()
