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
import json, os, re, subprocess, shutil, pathlib

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

# A moderately VERBOSE build: a plugin preamble (antrun banner) runs in process-test-classes, BEFORE
# surefire, so the `Tests run`/`BUILD` summary lands PAST the first ~1500 chars of `mvn test` output (the
# old front-truncation window) — reproducing the gson/bnd situation the trace-condense fix targets. Kept
# modest (~28 lines ≈ 2.7k chars) on purpose: enough to overshoot 1500 and exercise condensing, but NOT
# so large that the raw run_java output floods the agent's context (160 lines ≈ 20k did, starving the
# suspector/reproducer). Used by the `verbose` smoke repo below (repo["pom"] overrides the default POM).
_VERBOSE_BANNER = "\n".join(
    "      [verbose-build] initialising plugin component %03d of 28 (simulated multi-plugin preamble)" % i
    for i in range(28))
VERBOSE_POM = ("""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>verbose</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>
  <properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>junit</groupId><artifactId>junit</artifactId><version>4.13.2</version><scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-antrun-plugin</artifactId>
      <version>3.1.0</version>
      <executions><execution>
        <id>verbose-preamble</id>
        <phase>process-test-classes</phase>
        <goals><goal>run</goal></goals>
        <configuration><target>
          <echo>%BANNER%</echo>
        </target></configuration>
      </execution></executions>
    </plugin>
  </plugins></build>
</project>
""").replace("%BANNER%", _VERBOSE_BANNER)

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
            fix_token="pageSize - 1",
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
            fix_token="high - low",
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
            fix_token="(long)",
        ),
    ),
    # Derived from a real bug the pipeline flagged in google/gson TypeAdapters.LOCALE.read():
    # an empty locale string tokenizes to nothing, leaving language null -> new Locale(null) throws.
    dict(
        owner="synthbench", name="locale", art="locale",
        pkg="com/example/locale",
        src="LocaleParser.java",
        code='''package com.example.locale;

import java.util.Locale;
import java.util.StringTokenizer;

/** Parses an underscore-separated locale tag (e.g. "en_US") into a {@link Locale}. */
public final class LocaleParser {
    private LocaleParser() {}

    /**
     * Parses {@code tag} ("en", "en_US", "en_US_POSIX", ...) into a Locale.
     * An empty tag denotes "no locale" and returns {@link Locale#ROOT}.
     */
    public static Locale parse(String tag) {
        StringTokenizer st = new StringTokenizer(tag, "_");
        String language = null, country = "", variant = "";
        if (st.hasMoreTokens()) language = st.nextToken();
        if (st.hasMoreTokens()) country = st.nextToken();
        if (st.hasMoreTokens()) variant = st.nextToken();
        return new Locale(language, country, variant);
    }
}
''',
        oracle=dict(
            file="src/main/java/com/example/locale/LocaleParser.java",
            method="parse",
            symptom='An empty tag leaves language=null and new Locale(null, ...) throws NPE, but the contract says empty -> Locale.ROOT. (Minimized from gson TypeAdapters.LOCALE.read.)',
            repro="assertEquals(Locale.ROOT, LocaleParser.parse(\"\"));  // currently throws NullPointerException",
            fix="guard the empty tag: if (language == null) return Locale.ROOT;",
            fix_token="ROOT",
        ),
    ),
    # Same minimal bug shape, but a VERBOSE build (see VERBOSE_POM): the test summary lands far past the
    # first ~1500 chars of `mvn test`, so this is the smoke that exercises the trace-condense fix end to end.
    dict(
        owner="synthbench", name="verbose", art="verbose",
        pkg="com/example/verbose",
        src="Clamp.java",
        pom=VERBOSE_POM,
        code='''package com.example.verbose;

/** Confines a value to an inclusive range. */
public final class Clamp {
    private Clamp() {}

    /** Returns {@code v} confined to [{@code lo}, {@code hi}] (lo <= hi). */
    public static int clamp(int v, int lo, int hi) {
        return v < lo ? lo : v;
    }
}
''',
        oracle=dict(
            file="src/main/java/com/example/verbose/Clamp.java",
            method="clamp",
            symptom="Upper bound is never applied: clamp(10, 0, 5) returns 10 instead of 5.",
            repro="assertEquals(5, Clamp.clamp(10, 0, 5));",
            fix="also clamp above hi: v > hi ? hi : (v < lo ? lo : v)",
            fix_token="hi",
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
    # Also drop the harness's reused HEAD checkouts (<slug>__new-head/__old-head); otherwise a regenerate
    # updates the repo but the suspector keeps seeing a STALE checkout (old pom/tests) — which silently made
    # every verbose run use the old 160-line banner + no baseline test, so the fixes never took effect.
    for suffix in ("__new-head", "__old-head"):
        co = REPOS / (slug + suffix)
        if co.exists():
            shutil.rmtree(co)
    srcdir = d / "src" / "main" / "java" / repo["pkg"]
    srcdir.mkdir(parents=True)
    (d / "pom.xml").write_text(repo.get("pom") or POM.format(art=repo["art"]))
    (srcdir / repo["src"]).write_text(repo["code"])
    # A trivial baseline test so the module reads as TESTED in the repo map. Real repos have tests, so the
    # suspector engages; without one, a synth repo looks unconfirmable ("prefer TESTED modules") and the
    # suspector gets discouraged and often files 0 suspicions (flaky on paging, dead on verbose). The
    # reproducer still adds its own bug-specific failing test; this one just keeps the module confirmable.
    pkg = repo["pkg"].replace("/", ".")
    testdir = d / "src" / "test" / "java" / repo["pkg"]
    testdir.mkdir(parents=True)
    (testdir / "BaselineTest.java").write_text(
        f"package {pkg};\n\n"
        "import org.junit.Test;\n"
        "import static org.junit.Assert.assertTrue;\n\n"
        "/** Baseline test so this module is a TESTED module (the real bug test is added during repro). */\n"
        "public class BaselineTest {\n"
        "    @Test public void baseline() { assertTrue(true); }\n"
        "}\n")
    sh(["git", "init", "-q"], d)
    sh(["git", "add", "-A"], d)
    sh(["git", "-c", "user.email=bench@example.com", "-c", "user.name=bench",
        "commit", "-q", "-m", "initial commit"], d)
    sh(["git", "branch", "-M", "main"], d)
    sha = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return slug, dict(repo=f'{repo["owner"]}/{repo["name"]}', sha=sha, **repo["oracle"])


def generate():
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


def check(slug):
    """Assert the pipeline found AND fixed the planted bug for `slug`. Exit 0 = PASS, 1 = FAIL.

    The whole point of the self-assert: take the human (me) out of the smoke loop — no
    eyeballing reasoning logs. Reads the run JSON the pipeline wrote + the oracle, and
    checks (a) at least one bug was confirmed, (b) a fixed solution's diff touches the
    planted method, (c) the fix carries the expected token (the shape of the correct code).
    """
    key = slug.replace("/", "__")
    runp = ROOT / "results" / "susp_runs" / f"{key}__head.json"
    orap = ROOT / "results" / "synth_oracle.json"
    if not runp.exists():
        print(f"[FAIL] {slug}: no run json at {runp} (did the pipeline run?)"); return 1
    if not orap.exists():
        print(f"[FAIL] {slug}: no oracle at {orap} (run `synth_bench.py` to generate)"); return 1
    run = json.load(open(runp))
    oracle = json.load(open(orap)).get(key)
    if not oracle:
        print(f"[FAIL] {slug}: no oracle entry for {key}"); return 1
    method, token = oracle["method"], oracle.get("fix_token", "")
    ofile = (oracle.get("file") or "").split("/")[-1]   # planted source filename, e.g. Paginator.java
    sols = run.get("registry", {}).get("solutions", [])
    bugs_reg = run.get("registry", {}).get("bugs", [])
    loc_by_bug = {b.get("id"): (b.get("location") or "") for b in bugs_reg}
    found = run.get("bugs", 0) >= 1
    # Match the fixed solution to the planted bug by FILE (robust: a bare changed-line fix_diff carries
    # neither the method name nor the path, so the old `method in fix_diff` false-failed real fixes —
    # seen on paging). Fall back to method-name-in-diff.
    def _hits(s):
        loc = loc_by_bug.get(s.get("bug_id"), "")
        fd = s.get("fix_diff") or ""
        return bool((ofile and (ofile in loc or ofile in fd)) or (method in fd))
    fixed_sol = next((s for s in sols if s.get("fixed") and _hits(s)), None)
    fixed = fixed_sol is not None
    tok_ok = (not token) or (token in (fixed_sol.get("fix_diff", "") if fixed_sol else ""))
    # trace-quality: the stored before/after traces must carry the real surefire summary, not be empty or
    # front-truncated to build noise (the bug the condense fix targets — see VERBOSE_POM / `verbose` repo).
    bugs_reg = run.get("registry", {}).get("bugs", [])
    bug_trace = next((b.get("bug_trace", "") for b in bugs_reg if (b.get("bug_trace") or "").strip()), "")
    fix_rerun = (fixed_sol or {}).get("fix_rerun", "") if fixed_sol else ""
    trace_ok = ("Tests run:" in bug_trace) and bool(re.search(r"Tests run:\s*\d+,\s*Failures:\s*0", fix_rerun))
    ok = found and fixed and tok_ok and trace_ok
    print(f"[{'PASS' if ok else 'FAIL'}] {slug}: "
          f"found={found} fixed[{method}]={fixed} fix_token[{token!r}]={tok_ok} trace={trace_ok} "
          f"| suspicions={run.get('n_suspicions')} bugs={run.get('bugs')} solved={run.get('solved')}")
    if not trace_ok:
        print(f"       bug_trace[:80]={bug_trace[:80]!r}  fix_rerun[:80]={fix_rerun[:80]!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        sys.exit(check(sys.argv[2]))
    generate()
