import json
WEAK=[("eclipse-wildwebdeveloper__wildwebdeveloper__575",[0,1,2,3]),
      ("google__gson__head",[3]),
      ("SaptarshiSarkar12__Drifty__801",[2]),
      ("Aiven-Open__klaw__2296",[1]),
      ("brettwooldridge__HikariCP__head",[3]),
      ("qubole__rubix__423",[0])]
for tag,ids in WEAK:
    reg=json.load(open("results/susp_runs/%s.json"%tag))["registry"]
    bugs={b.get("id"):b for b in (reg.get("bugs") or [])}
    sols=reg.get("solutions") or []
    if isinstance(sols,dict): sols=list(sols.values())
    sol={s.get("bug_id"):s for s in sols}
    for i in ids:
        b=bugs.get(i,{}); s=sol.get(i,{})
        print("="*70)
        print("%s  bug=%s  R=%s fixed=%s test_changed=%s lines=%s"%(
            tag,i,s.get("reward"),s.get("fixed"),s.get("test_changed"),s.get("lines_changed")))
        print("  TITLE:", (b.get("title") or b.get("suspected_bug") or "")[:160])
        print("  has_test_src:", bool((b.get("test_src") or "").strip()))
        note=(s.get("rerun") or s.get("note") or s.get("fix_diff") or "")
        print("  SOLVER NOTE:", note[:320].replace("\n"," "))
