#!/usr/bin/env python3
"""iter1 (pre-coverage, archived) vs iter2 (coverage reward, live susp_runs). HEAD mode."""
import json, glob, os
def load(d):
    r={}
    for f in glob.glob(os.path.join(d,"*__head.json")):
        try: j=json.load(open(f))
        except: continue
        slug=os.path.basename(f).replace("__head.json","")
        r[slug]={"susp":j.get("n_suspicions",0) or 0,"bugs":j.get("bugs",0) or 0,"solved":j.get("solved",0) or 0}
    return r
a=load("results/archive/iter1/susp_runs"); b=load("results/susp_runs")
both=sorted(set(a)&set(b))
print(f"iter1 repos={len(a)}  iter2 repos={len(b)}  comparable(both)={len(both)}\n")
sa=sb=0
print(f"{'repo':42} {'iter1 b/s/su':>14} {'iter2 b/s/su':>14}  Δbugs")
for s in both:
    x,y=a[s],b[s]; sa+=x['bugs']; sb+=y['bugs']; d=y['bugs']-x['bugs']
    mark='  <<' if d>0 else ''
    print(f"{s:42} {x['bugs']:>3}/{x['solved']:>2}/{x['susp']:>2}    {y['bugs']:>3}/{y['solved']:>2}/{y['susp']:>2}   {d:+d}{mark}")
print(f"\nCONFIRMED BUGS on comparable repos: iter1={sa}  iter2={sb}  Δ={sb-sa:+d}  ({100*(sb-sa)/max(sa,1):+.0f}%)")
print(f"avg bugs/repo: iter1={sa/max(len(both),1):.2f} -> iter2={sb/max(len(both),1):.2f}")
