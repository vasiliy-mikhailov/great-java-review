"""Deterministic check of the scaffolding capture -> reset -> re-materialize round-trip (no LLM)."""
import sys, os; sys.path.insert(0, "src")
from current_version import sandbox as sb
from current_version.repo import ensure_repo_head
from current_version.suspicion import _write_scaffold, _scaffold_of

repo = "brettwooldridge/HikariCP"
d, sha = ensure_repo_head(repo)
sb.start(repo, "head", jdk=sb.detect_jdk(str(d)), log_path="results/probes/mechtest.log", new_ref="HEAD")
try:
    root = sb.workdir("new")
    helper = "src/test/java/com/zaxxer/hikari/mocks/StubMech.java"
    test   = "src/test/java/com/zaxxer/hikari/pool/MechTest.java"
    os.makedirs(os.path.join(root, os.path.dirname(helper)), exist_ok=True)
    os.makedirs(os.path.join(root, os.path.dirname(test)), exist_ok=True)
    open(os.path.join(root, helper), "w").write("package com.zaxxer.hikari.mocks;\npublic class StubMech { public static int x = 1; }\n")
    open(os.path.join(root, test), "w").write("package com.zaxxer.hikari.pool;\nclass MechTest { /* uses StubMech.x */ }\n")

    df = sb.dirty_files("new")
    cap = {p: c for p, c in df.items() if "/src/test/" in ("/" + p)}
    print("CAPTURED test-tree files:", sorted(cap.keys()))
    assert helper in cap, "helper stub NOT captured"
    assert test in cap, "test NOT captured"

    sb.reset_clean()
    print("after reset_clean -> helper present:", os.path.exists(os.path.join(root, helper)),
          "| test present:", os.path.exists(os.path.join(root, test)))

    # re-materialize via the same path solve() uses (scaffold = test_files superset, primary test ensured)
    scaffold = _scaffold_of(cap, test, cap[test])
    n = _write_scaffold(root, scaffold)
    print("re-materialized files:", n)
    identical = all(os.path.exists(os.path.join(root, p)) and open(os.path.join(root, p)).read() == c
                    for p, c in cap.items())
    print("ROUND-TRIP IDENTICAL (test_changed would be FALSE):", identical)
    print("RESULT:", "PASS" if (helper in cap and test in cap and identical) else "FAIL")
finally:
    sb.stop()
