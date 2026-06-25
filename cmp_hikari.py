import json
def rewards(path):
    reg=json.load(open(path))["registry"]
    sols=reg.get("solutions") or []
    if isinstance(sols,dict): sols=list(sols.values())
    bugs={b["id"]:b for b in reg["bugs"]}
    out=[]
    for s in sols:
        b=bugs.get(s.get("bug_id"),{})
        out.append((s.get("bug_id"), round(s.get("reward",0),3), s.get("fixed"),
                    s.get("lines_changed"), s.get("test_changed"),
                    len(b.get("test_files") or {}),
                    (b.get("suspected_bug") or b.get("title") or "")[:55].replace("\n"," ")))
    return out
print("=== OLD (pre-scaffold backup) ===")
for r in sorted(rewards("results/pre_scaffold_backup/brettwooldridge__HikariCP__head.json")):
    print(f"  bug{r[0]} R={r[1]} fixed={r[2]} lines={r[3]} test_changed={r[4]} tf={r[5]} | {r[6]}")
print("=== NEW (with scaffolding capture) ===")
for r in sorted(rewards("results/susp_runs/brettwooldridge__HikariCP__head.json")):
    print(f"  bug{r[0]} R={r[1]} fixed={r[2]} lines={r[3]} test_changed={r[4]} tf={r[5]} | {r[6]}")
