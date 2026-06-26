#!/usr/bin/env python3
"""Generate small synthetic Java repos with ONE planted, deterministic bug each.

A fast, offline smoke harness for the suspect->reproduce->fix pipeline (the live
analogue of the bump-java skill's minimal compile cases). Each repo is a real
local git repo under data/repos/<owner>__<name>, so `ensure_repo_head` reuses it
with no network, and the whole pipeline runs on it via:

    python -u src/current_version/suspicion.py <owner>/<name> head

Every planted bug is:
  * deterministic   — no concurrency/IO/clock; a plain unit test flips red->green
  * localized       — one method, a 1-2 line fix
  * real-shaped     — a genuine bug archetype, not a toy `assert false`

The oracle (file/line/symptom/fix) for each is written to
results/synth_oracle.json so a run can be checked against ground truth.

Run ON mh (writes into data/repos/):  python3 synth_bench.py
"""
import json, os, subprocess, shutil, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
REPOS = ROOT / "data" / "repos"

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>{art}</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>
  <properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
"""

# ----- repo definitions: each plants exactly one deterministic bug -----
BENCH = [
    dict(
        owner="synthbench", name="paging", art="paging",
        pkg="com/example/paging",
        src="Paginator.java",
        code='''package com.example.paging;

/** Splits a list of items into fixed-size pages. */
public final class Paginator {
    private Paginator() {}

    /**
     * Number of pages needed to show {@code totalItems} at {@code pageSize} per page.
     * The last, partially-filled page still counts as a page.
     */
    public static int pageCount(int totalItems, int pageSize) {
        if (pageSize <= 0) throw new IllegalArgumentException("pageSize must be > 0");
        return totalItems / pageSize;
    }

    /** Zero-based index of the page that holds the item at {@code itemIndex}. */
    public static int pageOf(int itemIndex, int pageSize) {
        return itemIndex / pageSize;
    }
}
''',
        oracle=dict(
            file="src/main/java/com/example/paging/Paginator.java",
            method="pageCount",
            symptom="Integer division drops the partial last page: pageCount(10,3)=3 but 4 pages are needed.",
            repro="assertEquals(4, Paginator.pageCount(10, 3));",
            fix="ceil division: (totalItems + pageSize - 1) / pageSize",
        ),
    ),
    dict(
        owner="synthbench", name="search", art="search",
        pkg="com/example/search",
        src="BinarySearch.java",
        code='''package com.example.search;

/** Index math for binary search over large offsets. */
public final class BinarySearch {
    private BinarySearch() {}

    /**
     * Midpoint offset between {@code low} and {@code high} (both >= 0, low <= high).
     * Must satisfy low <= midpoint(low,high) <= high.
     */
    public static int midpoint(int low, int high) {
        return (low + high) / 2;
    }
}
''',
        oracle=dict(
            file="src/main/java/com/example/search/BinarySearch.java",
            method="midpoint",
            symptom="(low+high) overflows int for large offsets: midpoint(MAX-1,MAX) is negative, breaking low<=mid<=high.",
            repro="int m = BinarySearch.midpoint(Integer.MAX_VALUE-1, Integer.MAX_VALUE); assertTrue(m >= Integer.MAX_VALUE-1);",
            fix="overflow-safe: low + (high - low) / 2",
        ),
    ),
    dict(
        owner="synthbench", name="ordering", art="ordering",
        pkg="com/example/ordering",
        src="AbsComparator.java",
        code='''package com.example.ordering;

import java.util.Comparator;

/** Orders integers by absolute value, smallest magnitude first. */
public final class AbsComparator implements Comparator<Integer> {
    @Override
    public int compare(Integer a, Integer b) {
        return Math.abs(a) - Math.abs(b);
    }
}
''',
        oracle=dict(
            file="src/main/java/com/example/ordering/AbsComparator.java",
            method="compare",
            symptom="Math.abs(Integer.MIN_VALUE) is negative and the subtraction overflows, so MIN_VALUE sorts as the smallest magnitude.",
            repro="sort [MIN_VALUE, 1, -1] with AbsComparator; MIN_VALUE must NOT come first.",
            fix="compare on widened longs: Long.compare(Math.abs((long)a), Math.abs((long)b))",
        ),
    ),
]


def sh(args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make(repo):
    slug = f'{repo["owner"]}__{repo["name"]}'
    d = REPOS / slug
    if d.exists():
        shutil.rmtree(d)
    srcdir = d / "src" / "main" / "java" / repo["pkg"]
    srcdir.mkdir(parents=True)
    (d / "pom.xml").write_text(POM.format(art=repo["art"]))
    (srcdir / repo["src"]).write_text(repo["code"])
    sh(["git", "init", "-q"], d)
    sh(["git", "add", "-A"], d)
    sh(["git", "-c", "user.email=bench@example.com", "-c", "user.name=bench",
        "commit", "-q", "-m", "initial commit"], d)
    sh(["git", "branch", "-M", "main"], d)
    sha = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return slug, dict(repo=f'{repo["owner"]}/{repo["name"]}', sha=sha, **repo["oracle"])


def main():
    REPOS.mkdir(parents=True, exist_ok=True)
    oracle = {}
    for repo in BENCH:
        slug, o = make(repo)
        oracle[slug] = o
        print(f"  built {slug}  ({o['method']} — {o['symptom'][:60]}...)")
    os.makedirs(ROOT / "results", exist_ok=True)
    (ROOT / "results" / "synth_oracle.json").write_text(json.dumps(oracle, indent=2))
    print(f"\n{len(oracle)} synthetic repos under data/repos/ ; oracle -> results/synth_oracle.json")
    print("run one:  python -u src/current_version/suspicion.py synthbench/paging head")


if __name__ == "__main__":
    main()
