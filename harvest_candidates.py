"""Append-only harvest of REAL judge verdicts into results/pr_candidates.jsonl, deduped by
(repo, location, suspected_bug). Continuous re-hunting overwrites the per-round judged JSONs, so this
preserves every REAL candidate ever found across rounds — the JSON is exploration, this is the ledger."""
import json, glob, os
OUT = "results/pr_candidates.jsonl"
seen = set()
if os.path.exists(OUT):
    for ln in open(OUT):
        try: seen.add(json.loads(ln)["key"])
        except Exception: pass
added = 0
for jf in sorted(glob.glob("results/judged/*__head.json")):
    try: d = json.load(open(jf))
    except Exception: continue
    repo = d.get("repo", "")
    for r in d.get("results", []):
        if str(r.get("verdict", "")).lower() != "real":
            continue
        key = f"{repo}|{r.get('location','')}|{str(r.get('suspected_bug',''))[:80]}"
        if key in seen:
            continue
        seen.add(key)
        with open(OUT, "a") as f:
            f.write(json.dumps({"key": key, "repo": repo, "id": r.get("id"),
                                "suspected_bug": r.get("suspected_bug", ""),
                                "location": r.get("location", ""),
                                "reason": r.get("reason", ""), "status": "open"}) + "\n")
        added += 1
print(f"harvested +{added} new REAL; ledger total {len(seen)}")
