import json
reg=json.load(open("results/susp_runs/brettwooldridge__HikariCP__head.json"))["registry"]
sols=reg.get("solutions") or []
if isinstance(sols,dict): sols=list(sols.values())
bugs={b["id"]:b for b in reg["bugs"]}
print("=== NEW HikariCP run (scaffolding capture + new prompts) ===")
for s in sorted(sols,key=lambda x:x.get("bug_id",0)):
    b=bugs.get(s.get("bug_id"),{})
    tf=len(b.get("test_files") or {})
    print(f"  bug{s.get('bug_id')} R={round(s.get('reward',0),3)} fixed={s.get('fixed')} "
          f"lines={s.get('lines_changed')} test_changed={s.get('test_changed')} test_files={tf} "
          f"| {(b.get('suspected_bug') or '')[:60]}")
# any multi-file-test bugs?
multi=[(b['id'],len(b.get('test_files') or {})) for b in reg['bugs'] if len(b.get('test_files') or {})>1]
print("multi-file-test bugs (test_files>1):", multi)
