"""Re-run ONLY the solve stage on stored weak Bugs, with the updated solver prompt.
Cheap: skips investigate/reproduce, re-materializes the bug's own stored test, re-solves from clean.
Tests the hypothesis: weak (R=0) solutions become strong with the reason-about-correctness solver."""
import sys, json; sys.path.insert(0, "src")
from current_version.suspicion import solve, _setup_head, _setup, _sandbox, Bug

# Mode B targets: solver previously CHEATED (test_changed=True -> R=0). tag -> [bug_ids, old_reward]
TARGETS = [
    ("brettwooldridge__HikariCP__head", [3]),   # setSchema 2-line fix; was R=0 (touched test)
    ("google__gson__head",              [3]),   # RuntimeTypeAdapterFactory CCE; was R=0 (touched test)
    ("SaptarshiSarkar12__Drifty__801",  [2]),   # native-image resource-config; was R=0 (touched test)
]

def _reward(fix, bug):
    passes = fix["fixed"] and bool(bug.test_src)
    return (1.0 if passes else 0.0) * (0.9 ** fix["lines_changed"]) * (0.0 if fix["test_changed"] else 1.0)

def _setup_for(tag, d_repo):
    if tag.endswith("__head"):
        repo = tag[:-len("__head")].replace("__", "/")
        d, pi, t, sha = _setup_head(repo)
        _sandbox.start(repo, "head", jdk=_sandbox.detect_jdk(d),
                       log_path=f"results/probes/{t}.log", new_ref="HEAD")
        return d
    parts = tag.split("__"); pr = int(parts[-1]); repo = "/".join(parts[:-1])
    d, pi, t = _setup(repo, pr)
    _sandbox.start(repo, pr, jdk=_sandbox.detect_jdk(d), log_path=f"results/probes/{t}.log")
    return d

out = []
for tag, ids in TARGETS:
    reg = json.load(open(f"results/susp_runs/{tag}.json"))["registry"]
    bugs = {b["id"]: b for b in reg["bugs"]}
    try:
        d = _setup_for(tag, None)
    except Exception as e:
        print(f"!! setup failed {tag}: {e}", flush=True); continue
    try:
        for i in ids:
            bug = Bug(**bugs[i])
            print(f"\n>>> RESOLVE {tag} bug={i}  ({bug.location})", flush=True)
            fix = solve(d, bug)
            r = _reward(fix, bug)
            rec = {"tag": tag, "bug": i, "fixed": fix["fixed"],
                   "lines_changed": fix["lines_changed"], "test_changed": fix["test_changed"],
                   "new_reward": round(r, 4), "fix_diff": (fix.get("fix_diff") or "")[:400]}
            out.append(rec)
            print(f"<<< {tag} bug={i}: OLD R=0.0  ->  NEW fixed={fix['fixed']} "
                  f"lines={fix['lines_changed']} test_changed={fix['test_changed']} R={r:.4f}", flush=True)
    finally:
        _sandbox.stop()

json.dump(out, open("results/resolve_weak.json", "w"), indent=1)
print("\n=== SUMMARY ===")
for r in out:
    print(f"{r['tag']} bug={r['bug']}: 0.0 -> {r['new_reward']} "
          f"(fixed={r['fixed']}, lines={r['lines_changed']}, test_changed={r['test_changed']})")
