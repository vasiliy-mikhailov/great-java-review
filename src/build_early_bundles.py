"""Build diff-grounded early-judge bundles for v8 reviews generated so far.

Safe alongside the running container: reads a SNAPSHOT of the OUT file, recovers
empties from traces in-memory (no OUT write), pulls the PR diff + human reference
from the dataset cache (no git, no GitHub). Writes results/claude_judge/early_<pr>.json.

  python3 src/build_early_bundles.py
"""
from __future__ import annotations
import json, os, shutil, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recover_empties import recover_from_trace  # noqa: E402
import dataset as ds  # noqa: E402

OUT = "results/threeway_v8_elite.json"
TRACE_DIR = "results/traces_v8_elite"
ELITE = "results/threeway_prs_elite.json"
BUNDLE_DIR = "results/claude_judge"


def main():
    snap = OUT + ".snap"
    shutil.copyfile(OUT, snap)          # near-atomic read; avoid catching a partial write
    recs = json.load(open(snap))
    os.remove(snap)
    elite = {r["pr"]: r for r in json.load(open(ELITE))}
    imap = {(x["repo"], int(x["pr"])): x for v in ds.build_instances().values() for x in v}
    os.makedirs(BUNDLE_DIR, exist_ok=True)
    built, empty = [], []
    for r in recs:
        repo, pr = r["repo"], r["pr"]
        text = r.get("text", "")
        if len(text) < 200:             # recover from trace, in-memory only
            tag = repo.replace("/", "__") + "__" + str(pr)
            tp = f"{TRACE_DIR}/{tag}__orch.json"
            try:
                text = recover_from_trace(tp)
            except FileNotFoundError:
                text = ""
        if len(text) < 200:
            empty.append(pr); continue
        x = imap.get((repo, int(pr))) or {}
        e = elite.get(pr, {})
        bundle = {
            "repo": repo, "pr": pr,
            "kind": e.get("kind"), "elite_depth": e.get("elite_depth"),
            "diff": x.get("input", ""),                 # PR title + diff (dataset; offline)
            "human_reference": x.get("reference_review", ""),
            "v8_review": text,
        }
        json.dump(bundle, open(f"{BUNDLE_DIR}/early_{pr}.json", "w"), indent=1)
        built.append(pr)
    print(f"built {len(built)} bundles: {sorted(built)}")
    if empty:
        print(f"still empty (no trace review): {empty}")


if __name__ == "__main__":
    main()
