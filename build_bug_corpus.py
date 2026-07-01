#!/usr/bin/env python3
"""Build a bug benchmark corpus: join GitHub PR data with internal susp_runs suspicions.
Fields per bug: bug, repo+sha/branch url, filename, suspicion, unit_test, fix, owner comments, final state.
Re-runnable (fetches live PR state each run). Usage: python3 build_bug_corpus.py [--only repo#num]"""
import json, subprocess, sys, os, glob, re, time

CURATED = [
  "ReactiveX/RxJava#8149","ReactiveX/RxJava#8159",
  "SeleniumHQ/selenium#17713","SeleniumHQ/selenium#17714",
  "alibaba/Sentinel#3629","alibaba/Sentinel#3630",
  "alibaba/arthas#3221",
  "alibaba/canal#5592","alibaba/canal#5593",
  "alibaba/druid#6660",
  "alibaba/nacos#15410","alibaba/nacos#15415",
  "apache/commons-collections#692","apache/commons-collections#693",
  "apolloconfig/apollo#5634","apolloconfig/apollo#5635",
  "brettwooldridge/HikariCP#2405","brettwooldridge/HikariCP#2406",
  "brettwooldridge/HikariCP#2407","brettwooldridge/HikariCP#2408","brettwooldridge/HikariCP#2409",
  "chinabugotech/hutool#4273","chinabugotech/hutool#4274","chinabugotech/hutool#4275","chinabugotech/hutool#4276",
  "google/gson#3038","google/gson#3039",
  "google/guava#8499",
  "keycloak/keycloak#50289",
  "mybatis/mybatis-3#3716","mybatis/mybatis-3#3717",
  "redisson/redisson#7215","redisson/redisson#7216",
  "skylot/jadx#2898","skylot/jadx#2899",
  "zxing/zxing#2107","zxing/zxing#2108",
]
ME = "vasiliy-mikhailov"
BOT = re.compile(r"\[bot\]$|^CLAassistant$|^codecov", re.I)


def gh(args):
    try:
        out = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return None
        return out.stdout
    except Exception:
        return None


def gh_json(args):
    s = gh(args)
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def is_test(path):
    b = os.path.basename(path)
    return ("/test/" in path or "/tests/" in path or
            re.search(r"(Test|Tests|TestCase|Spec|IT)\.java$", b) or b.startswith("Test"))


def split_diff(diff):
    """Return {path: hunk_text} for each file in a unified diff."""
    files = {}
    if not diff:
        return files
    cur = None
    buf = []
    for line in diff.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            if cur is not None:
                files[cur] = "\n".join(buf)
            cur = m.group(2)
            buf = [line]
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        files[cur] = "\n".join(buf)
    return files


def load_susp_index():
    """(repo, basename) -> list of {observation, suspected_bug, location, confidence, status}."""
    idx = {}
    for f in glob.glob(os.path.expanduser("~/fix-java-bugs/results/susp_runs/*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        repo = d.get("repo")
        reg = d.get("registry")
        items = []
        if isinstance(reg, dict):
            for v in reg.values():
                items += v if isinstance(v, list) else [v]
        elif isinstance(reg, list):
            items = reg
        for e in items:
            if not isinstance(e, dict):
                continue
            loc = str(e.get("location", ""))
            base = os.path.basename(loc.split(":")[0]) if loc else ""
            if not base:
                continue
            idx.setdefault((repo, base), []).append(
                {k: e.get(k) for k in ("observation", "suspected_bug", "location", "confidence", "status")})
    return idx


def _changed_old_ranges(diff_text):
    rs = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))?", diff_text or "", re.M):
        st = int(m.group(1))
        cnt = int(m.group(2) or 1)
        rs.append((st - 3, st + cnt + 3))
    return rs


def _loc_line(loc):
    m = re.search(r":(\d+)", str(loc) or "")
    return int(m.group(1)) if m else None


def match_suspicion(idx, repo, fix_files, fix_diff):
    cands = []
    for fp in fix_files:
        cands += idx.get((repo, os.path.basename(fp)), [])
    # dedup by (location, suspected_bug-prefix), preferring entries that carry a status
    seen = {}
    for c in cands:
        k = (str(c.get("location")), str(c.get("suspected_bug"))[:60])
        if k not in seen or (c.get("status") and not seen[k].get("status")):
            seen[k] = c
    cands = list(seen.values())
    if not cands:
        return None
    ranges = _changed_old_ranges(fix_diff)
    in_range = []
    for c in cands:
        ln = _loc_line(c.get("location"))
        if ln is not None and any(a <= ln <= b for a, b in ranges):
            in_range.append(c)
    chosen = in_range if in_range else cands
    tag = "line" if in_range else "file"
    for c in chosen:
        c["_match"] = tag
    return chosen


def build_entry(slug, susp_idx):
    repo, num = slug.split("#")
    num = int(num)
    pr = gh_json(["api", f"repos/{repo}/pulls/{num}"])
    if not pr:
        return {"id": slug, "repo": repo, "pr_number": num, "error": "pr fetch failed"}
    state = "merged" if pr.get("merged") else pr.get("state", "").lower()
    diff = gh(["pr", "diff", str(num), "--repo", repo])
    files = split_diff(diff)
    fix_files = [p for p in files if not is_test(p)]
    test_files = [p for p in files if is_test(p)]
    # comments: issue + review-thread + review summaries, humans only
    comments = []
    for ep, kind in [(f"repos/{repo}/issues/{num}/comments", "issue"),
                     (f"repos/{repo}/pulls/{num}/comments", "review_inline")]:
        arr = gh_json(["api", "--paginate", ep]) or []
        for c in arr:
            u = (c.get("user") or {}).get("login", "")
            if u == ME or BOT.search(u or ""):
                continue
            comments.append({"user": u, "kind": kind, "created": c.get("created_at"),
                             "path": c.get("path"), "body": (c.get("body") or "").strip()})
    revs = gh_json(["api", f"repos/{repo}/pulls/{num}/reviews"]) or []
    for r in revs:
        u = (r.get("user") or {}).get("login", "")
        if u == ME or BOT.search(u or "") or not (r.get("body") or "").strip():
            continue
        comments.append({"user": u, "kind": "review", "created": r.get("submitted_at"),
                         "state": r.get("state"), "body": (r.get("body") or "").strip()})
    comments.sort(key=lambda c: c.get("created") or "")
    base_sha = (pr.get("base") or {}).get("sha")
    fix_diff_txt = "\n".join(files[p] for p in fix_files)
    susp = match_suspicion(susp_idx, repo, fix_files, fix_diff_txt)
    return {
        "id": slug, "repo": repo, "pr_number": num, "pr_url": pr.get("html_url"),
        "title": pr.get("title"),
        "bug": (pr.get("body") or "").strip(),
        "filename": fix_files,
        "base_sha": base_sha, "head_sha": (pr.get("head") or {}).get("sha"),
        "merge_commit_sha": pr.get("merge_commit_sha"),
        "base_branch": (pr.get("base") or {}).get("ref"),
        "code_url": [f"https://github.com/{repo}/blob/{base_sha}/{p}" for p in fix_files] if base_sha else [],
        "suspicion": susp,
        "unit_test": {"files": test_files, "diff": "\n".join(files[p] for p in test_files)},
        "fix": {"files": fix_files, "diff": fix_diff_txt},
        "owner_comments": comments,
        "final_state": state,
        "merged": bool(pr.get("merged")),
        "merged_by": (pr.get("merged_by") or {}).get("login") if pr.get("merged_by") else None,
    }


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    susp_idx = load_susp_index()
    sys.stderr.write(f"susp index: {len(susp_idx)} (repo,file) keys\n")
    targets = [only] if only else CURATED
    out = []
    for i, slug in enumerate(targets):
        sys.stderr.write(f"[{i+1}/{len(targets)}] {slug}\n")
        sys.stderr.flush()
        out.append(build_entry(slug, susp_idx))
        time.sleep(0.3)
    if only:
        print(json.dumps(out[0], indent=2))
        return
    os.makedirs(os.path.expanduser("~/fix-java-bugs/results/bug_corpus"), exist_ok=True)
    cp = os.path.expanduser("~/fix-java-bugs/results/bug_corpus/corpus.jsonl")
    with open(cp, "w") as f:
        for e in out:
            f.write(json.dumps(e) + "\n")
    ip = os.path.expanduser("~/fix-java-bugs/results/bug_corpus/INDEX.md")
    with open(ip, "w") as f:
        f.write("# Bug benchmark corpus\n\n")
        by_state = {}
        for e in out:
            by_state.setdefault(e.get("final_state", "?"), []).append(e)
        n_susp = sum(1 for e in out if e.get("suspicion"))
        f.write(f"{len(out)} bugs | " + " | ".join(f"{k}: {len(v)}" for k, v in sorted(by_state.items())) +
                f" | with suspicion: {n_susp}\n\n")
        f.write("| bug | state | file | suspicion | test | owner cmts |\n|---|---|---|---|---|---|\n")
        for e in out:
            fn = ", ".join(os.path.basename(p) for p in e.get("filename", [])) or "-"
            sm = e.get("suspicion")
            susp_cell = (sm[0].get("_match") if sm else "no")
            has_test = "yes" if e.get("unit_test", {}).get("files") else "no"
            ncmt = len(e.get("owner_comments", []))
            f.write("| [%s](%s) | %s | %s | %s | %s | %s |\n" % (
                e["id"], e.get("pr_url", ""), e.get("final_state"), fn, susp_cell, has_test, ncmt))
    sys.stderr.write(f"wrote {cp} and {ip} ({len(out)} entries)\n")


if __name__ == "__main__":
    main()
