"""Phase-2 sample: keep the frozen 37 reproduction PRs, add N test-review PRs.

A "test-review unit" = the PR's diff touches test code AND the human reference
review substantively discusses the tests (test terms present, >=2 review points).
This makes the expanded eval measure unit-test review quality, not just
production-code review. Deterministic (seeded), stratified round-robin by repo.

  ./venv-oh/bin/python -u src/sample_tests.py 38 results/threeway_prs_75.json
"""
from __future__ import annotations
import json, re, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import random
import dataset as ds  # noqa: E402

GIANT = {"JetBrains/intellij-community", "eclipse-platform/eclipse.platform.swt"}
FROZEN = "results/threeway_prs.json"   # the 37 reproduction PRs — kept as-is
TESTPATH = re.compile(r"(/src/test/|/test/java/|Test[s]?\.java|IT\.java|[A-Za-z]+Test\b|"
                      r"@Test|junit|assertThat|assertEquals|mock\(|Mockito)", re.I)
TESTREV = re.compile(r"\b(test|assert|mock|stub|coverage|junit|@Test|testcase|"
                     r"edge case|fixture|parameteriz)\b", re.I)


def qualifies(x):
    inp = x.get("input", "") or ""
    rev = x.get("reference_review", "") or ""
    L = len(inp); hum = len(rev.strip())
    return (x["repo"] not in GIANT and 1500 <= L <= 60000 and hum >= 120
            and (x.get("n_points") or 0) >= 2
            and TESTPATH.search(inp) and len(TESTREV.findall(rev)) >= 1)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 38
    out = sys.argv[2] if len(sys.argv) > 2 else "results/threeway_prs_75.json"
    frozen = json.load(open(FROZEN))
    frozen_keys = {(r["repo"], int(r["pr"])) for r in frozen}

    xs = [x for v in ds.build_instances().values() for x in v]
    pool = [x for x in xs if qualifies(x) and (x["repo"], int(x["pr"])) not in frozen_keys]
    rng = random.Random(20260613)
    rng.shuffle(pool)
    by_repo: dict = {}
    for p in pool:
        by_repo.setdefault(p["repo"], []).append(p)
    repos = sorted(by_repo, key=lambda r: -len(by_repo[r]))
    rng.shuffle(repos)
    picked, i, seen = [], 0, set()
    while len(picked) < n and any(by_repo.values()):
        r = repos[i % len(repos)]
        if by_repo[r]:
            x = by_repo[r].pop()
            k = (x["repo"], int(x["pr"]))
            if k not in seen:
                seen.add(k)
                picked.append({"repo": x["repo"], "pr": int(x["pr"]),
                               "reviewer": x.get("reviewer"),
                               "diff_chars": len(x["input"] or ""),
                               "human_chars": len((x["reference_review"] or "").strip()),
                               "n_points": x.get("n_points"), "test_review": True})
        i += 1
    combined = frozen + picked
    json.dump(combined, open(out, "w"), indent=2)
    print(f"frozen={len(frozen)} + test-review picked={len(picked)} = {len(combined)} -> {out}", flush=True)
    for p in picked:
        print(f"  {p['repo']:38}#{p['pr']:<7} diff={p['diff_chars']:>6} "
              f"pts={p['n_points']} {p['reviewer']}", flush=True)


if __name__ == "__main__":
    main()
