"""Pick a seeded, size-filtered RANDOM sample of PRs (not cherry-picked) for the 3-way
grounded comparison, stratified across repos, excluding the 4 already captured.

  ./venv-oh/bin/python -u src/sample_prs.py 12
"""
from __future__ import annotations
import json, os, random, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import dataset as ds  # noqa: E402

# multi-GB repos GitHub throttles to ~5 MB/min — a full clone wedges the run for hours.
GIANT = {"JetBrains/intellij-community", "eclipse-platform/eclipse.platform.swt"}
OUT = "results/threeway_prs.json"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    inst = ds.build_instances()
    seen, pool = set(), []
    for x in (x for v in inst.values() for x in v):
        key = (x["repo"], int(x["pr"]))
        if key in seen or x["repo"] in GIANT:
            continue
        seen.add(key)
        L = len(x["input"] or "")
        hum = len((x["reference_review"] or "").strip())
        # real review, non-trivial diff, but not a monster that blows context / takes hrs
        if 1500 <= L <= 60000 and hum >= 120:
            pool.append({"repo": x["repo"], "pr": int(x["pr"]),
                         "reviewer": x.get("reviewer"), "diff_chars": L, "human_chars": hum})
    rng = random.Random(20260610)
    rng.shuffle(pool)
    # stratify: round-robin by repo so we don't draw 12 from quarkus alone
    by_repo: dict = {}
    for p in pool:
        by_repo.setdefault(p["repo"], []).append(p)
    repos = sorted(by_repo, key=lambda r: -len(by_repo[r]))
    rng.shuffle(repos)
    picked, i = [], 0
    while len(picked) < n and any(by_repo.values()):
        r = repos[i % len(repos)]
        if by_repo[r]:
            picked.append(by_repo[r].pop())
        i += 1
    json.dump(picked, open(OUT, "w"), indent=2)
    print(f"pool={len(pool)} picked={len(picked)} -> {OUT}", flush=True)
    for p in picked:
        print(f"  {p['repo']:38}#{p['pr']:<7} diff={p['diff_chars']:>6} "
              f"human={p['human_chars']:>5} {p['reviewer']}", flush=True)


if __name__ == "__main__":
    main()
