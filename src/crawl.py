"""Mine GitHub for high-signal Java code reviewers and their reviews.

The real substance of code review on big Java repos lives in *inline review
comments*, not always in the formal review body. So discovery is built on the
cheap repo-level endpoint ``/repos/{repo}/pulls/comments`` (100 inline comments
per call), grouping comments into "review units" keyed by pull_request_review_id.

Phases (resumable, single-worker):

  discover  Stream recent inline review comments for each configured Java repo;
            store every comment as a stub; group into review units; tally and
            rank reviewers by number of *substantive* review units.

  collect   For the chosen top-N reviewers, take up to K substantive review
            units each, enrich with PR context (title/body/diff) and the formal
            review body/state, and write excellent_reviews.json.

Usage:
  python src/crawl.py discover
  python src/crawl.py rank
  python src/crawl.py collect
  python src/crawl.py all
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from gh_client import GitHub  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
RAW = ROOT / "data" / "raw"
CACHE.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
GH_CFG = CFG["github"]
SEL = CFG["selection"]

COMMENTS_INDEX = CACHE / "comments_index.jsonl"
DISCOVERY_STATE = CACHE / "discovery_state.json"
TALLY = CACHE / "tally.json"
RANKED = CACHE / "ranked_reviewers.json"
OUT_PATH = ROOT / "excellent_reviews.json"

BAD_SUFFIX = "[bot]"
KNOWN_BOTS = {"copilot", "dependabot", "github-actions", "renovate",
              "codecov", "sonarcloud", "mergify", "elasticmachine",
              "elasticsearchmachine", "spring-projects-issues"}


def is_bot(login: str | None) -> bool:
    if not login:
        return True
    lo = login.lower()
    return lo.endswith(BAD_SUFFIX) or lo in KNOWN_BOTS or lo.endswith("-bot")


def load_json(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def pr_num_from_url(url: str) -> int | None:
    # https://api.github.com/repos/o/r/pulls/123
    try:
        return int(url.rstrip("/").split("/")[-1])
    except Exception:  # noqa: BLE001
        return None


def comment_score(body: str) -> float:
    body = body or ""
    s = min(len(body), 1500) / 150.0
    for kw in ("should", "instead", "consider", "why", "prefer", "null",
               "thread", "race", "leak", "test", "edge", "npe", "synchron",
               "deadlock", "allocat", "immutable", "exception", "boundary"):
        if kw in body.lower():
            s += 0.3
    s += body.count("```") * 0.6      # code suggestions
    s += body.count("\n- ") * 0.2     # enumerated points
    return s


# ---------------------------------------------------------------------------
def _load_seen_ids():
    seen = set()
    if COMMENTS_INDEX.exists():
        for line in COMMENTS_INDEX.read_text().splitlines():
            if line.strip():
                try:
                    seen.add(json.loads(line)["comment_id"])
                except Exception:  # noqa: BLE001
                    pass
    return seen


def _distinct_reviewers():
    seen = set()
    if COMMENTS_INDEX.exists():
        for line in COMMENTS_INDEX.read_text().splitlines():
            if line.strip():
                try:
                    lo = json.loads(line)["login"]
                    if not is_bot(lo):
                        seen.add(lo)
                except Exception:  # noqa: BLE001
                    pass
    return seen


def _stream_repo(gh, repo, cap, fout, seen_ids, state, reviewers=None):
    """Stream up to `cap` recent inline comments of one repo into the index.

    Never raises: on any error it checkpoints and returns, so a long progressive
    crawl always advances to the next repo. Returns #comments streamed."""
    print(f"[stream] {repo}: up to {cap} inline comments")
    count = 0
    try:
        for c in gh.paginate(
            f"/repos/{repo}/pulls/comments",
            {"sort": "created", "direction": "desc"},
            max_items=cap,
        ):
            count += 1
            cid = c.get("id")
            if cid in seen_ids:
                continue
            user = (c.get("user") or {}).get("login")
            if is_bot(user):
                continue
            pr = pr_num_from_url(c.get("pull_request_url", ""))
            if pr is None:
                continue
            rec = {
                "login": user, "repo": repo, "pr": pr,
                "review_id": c.get("pull_request_review_id"),
                "comment_id": cid, "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "diff_hunk": (c.get("diff_hunk") or "")[:1500],
                "body": c.get("body", ""),
                "created_at": c.get("created_at"),
                "author_association": c.get("author_association"),
            }
            fout.write(json.dumps(rec) + "\n")
            seen_ids.add(cid)
            if reviewers is not None:
                reviewers.add(user)
            if count % 500 == 0:
                fout.flush()
                state["repos"].setdefault(repo, {})["scanned"] = count
                DISCOVERY_STATE.write_text(json.dumps(state, indent=2))
                print(f"    {repo}: {count}/{cap} comments, {gh.calls} calls, "
                      f"{len(seen_ids)} indexed")
    except Exception as e:  # noqa: BLE001
        fout.flush()
        state["repos"].setdefault(repo, {})["scanned"] = count
        DISCOVERY_STATE.write_text(json.dumps(state, indent=2))
        print(f"[stream] {repo} stopped at {count}: {e}")
        return count
    state["repos"][repo] = {"scanned": count, "done": True}
    DISCOVERY_STATE.write_text(json.dumps(state, indent=2))
    fout.flush()
    return count


def discover():
    gh = GitHub(min_interval=GH_CFG["min_request_interval_s"])
    state = load_json(DISCOVERY_STATE, {"repos": {}})
    scan_n = GH_CFG["per_repo_comment_scan"]
    seen_ids = _load_seen_ids()
    print(f"[discover] {len(seen_ids)} comments already indexed")
    fout = COMMENTS_INDEX.open("a")
    for repo in GH_CFG["seed_repos"]:
        if state["repos"].get(repo, {}).get("done"):
            print(f"[discover] {repo}: done, skip")
            continue
        _stream_repo(gh, repo, scan_n, fout, seen_ids, state)
    fout.close()
    rank()


# ---------------------------------------------------------------------------
REPOS_CACHE = CACHE / "java_repos.json"


def discover_java_repos(gh, want):
    """Enumerate popular language:Java repos via star-bucketed search.

    GitHub caps any single search at 1000 results, so we page across star
    ranges to reach far more repos. Cached + deduped against seed repos."""
    wcfg = GH_CFG.get("wide", {})
    repos = list(dict.fromkeys(load_json(REPOS_CACHE, {"repos": []})["repos"]))
    have = set(repos) | set(GH_CFG["seed_repos"])
    for lo, hi in wcfg.get("star_buckets", []):
        if len(repos) >= want:
            break
        q = (f"language:Java stars:{lo}..{hi}" if hi
             else f"language:Java stars:>={lo}")
        try:
            for r in gh.paginate("/search/repositories",
                                 {"q": q, "sort": "stars", "order": "desc",
                                  "per_page": 100}, max_items=1000):
                full = r.get("full_name")
                if not full or full in have or r.get("archived"):
                    continue
                repos.append(full)
                have.add(full)
                if len(repos) >= want:
                    break
        except Exception as e:  # noqa: BLE001
            print(f"[repos] bucket {lo}..{hi} error: {e}")
        REPOS_CACHE.write_text(json.dumps({"repos": repos}, indent=2))
        print(f"[repos] {len(repos)} java repos discovered (bucket {lo}..{hi})")
    return repos


def wide():
    """Progressive wide crawl: keep adding repos until the distinct-reviewer
    pool is big enough for the Fibonacci sweep up to max_k (~10k). Resumable."""
    wcfg = GH_CFG.get("wide", {})
    target = wcfg.get("target_reviewers", 11000)
    max_repos = wcfg.get("max_repos", 800)
    cap = wcfg.get("per_repo_comment_scan", 1200)
    gh = GitHub(min_interval=GH_CFG["min_request_interval_s"])
    state = load_json(DISCOVERY_STATE, {"repos": {}})
    seen_ids = _load_seen_ids()
    reviewers = _distinct_reviewers()
    print(f"[wide] start: {len(reviewers)} distinct reviewers, target {target}")

    repos = discover_java_repos(gh, max_repos)
    todo = [r for r in (GH_CFG["seed_repos"] + repos)
            if not state["repos"].get(r, {}).get("done")]
    print(f"[wide] {len(todo)} repos to crawl")
    fout = COMMENTS_INDEX.open("a")
    crawled = 0
    for repo in todo:
        if len(reviewers) >= target or crawled >= max_repos:
            break
        _stream_repo(gh, repo, cap, fout, seen_ids, state, reviewers)
        crawled += 1
        print(f"[wide] {crawled} repos crawled this run, "
              f"{len(reviewers)} distinct reviewers (target {target})")
    fout.close()
    rank()
    print(f"[wide] DONE: {len(reviewers)} distinct reviewers in pool")


# ---------------------------------------------------------------------------
def _review_units():
    """Group indexed comments into review units keyed by (repo,pr,review_id)."""
    units = defaultdict(lambda: {"comments": [], "logins": set()})
    if not COMMENTS_INDEX.exists():
        return {}
    for line in COMMENTS_INDEX.read_text().splitlines():
        if not line.strip():
            continue
        try:                       # tolerate a torn last line if the wide crawl
            c = json.loads(line)   # is concurrently appending to the index
        except Exception:          # noqa: BLE001
            continue
        if is_bot(c.get("login")):
            continue
        rid = c.get("review_id") or f"loose-{c['pr']}-{c['login']}"
        key = (c["repo"], c["pr"], rid, c["login"])
        units[key]["comments"].append(c)
    return units


def is_substantive_unit(comments: list) -> bool:
    if len(comments) >= SEL["min_inline_comments"]:
        return True
    return any(len(c.get("body", "")) >= SEL["min_body_chars"] for c in comments)


def rank():
    units = _review_units()
    by_login = defaultdict(lambda: {"units": 0, "subst": 0, "comments": 0,
                                    "score": 0.0, "repos": set(), "prs": set()})
    for (repo, pr, rid, login), u in units.items():
        cs = u["comments"]
        d = by_login[login]
        d["units"] += 1
        d["comments"] += len(cs)
        d["repos"].add(repo)
        d["prs"].add((repo, pr))
        usc = sum(comment_score(c["body"]) for c in cs)
        d["score"] += usc
        if is_substantive_unit(cs):
            d["subst"] += 1

    rows = []
    for login, d in by_login.items():
        rows.append({
            "login": login,
            "substantive_reviews": d["subst"],
            "total_review_units": d["units"],
            "total_comments": d["comments"],
            "total_score": round(d["score"], 1),
            "n_repos": len(d["repos"]),
            "repos": sorted(d["repos"]),
            "n_prs": len(d["prs"]),
        })
    need = SEL["reviews_per_reviewer"]
    rows.sort(key=lambda x: (
        x["substantive_reviews"] >= need,
        x["n_repos"],
        x["total_score"],
    ), reverse=True)
    TALLY.write_text(json.dumps(rows, indent=2))
    top = [r for r in rows if r["substantive_reviews"] >= max(20, need // 3)]
    RANKED.write_text(json.dumps(top[: SEL["num_reviewers"] * 3], indent=2))
    nfull = len([r for r in rows if r["substantive_reviews"] >= need])
    print(f"[rank] {len(rows)} reviewers; {nfull} have >= {need} substantive "
          f"review units.")
    for r in rows[:20]:
        print(f"  {r['login']:24s} subst={r['substantive_reviews']:4d} "
              f"units={r['total_review_units']:4d} repos={r['n_repos']} "
              f"score={r['total_score']}")


# ---------------------------------------------------------------------------
def _pr_context(gh: GitHub, repo: str, num: int, char_budget: int = 6000):
    pr = gh.get(f"/repos/{repo}/pulls/{num}")
    if not pr:
        return None
    files = list(gh.paginate(f"/repos/{repo}/pulls/{num}/files", max_items=60))
    parts, used = [], 0
    for f in files:
        header = (f"\n--- {f.get('filename')} "
                  f"(+{f.get('additions')}/-{f.get('deletions')}) ---\n")
        parts.append(header); used += len(header)
        patch = f.get("patch")
        if patch:
            take = patch[: max(0, char_budget - used)]
            parts.append(take); used += len(take)
        if used >= char_budget:
            parts.append("\n[... diff truncated ...]"); break
    return {
        "title": pr.get("title", ""),
        "body": (pr.get("body") or "")[:4000],
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "changed_files": pr.get("changed_files"),
        "diff": "".join(parts),
        "files": [f.get("filename") for f in files],
        "html_url": pr.get("html_url"),
    }


def _units_for_pr(gh, repo, num, login):
    """Build this reviewer's substantive review-units on one PR.

    A unit = comments grouped by pull_request_review_id (+ the formal review
    body/state for that id). Returns list of unit dicts (may be empty).
    """
    comments = list(gh.paginate(f"/repos/{repo}/pulls/{num}/comments",
                                max_items=300))
    mine = [c for c in comments if (c.get("user") or {}).get("login") == login]
    if not mine:
        return []
    groups = defaultdict(list)
    for c in mine:
        rid = c.get("pull_request_review_id") or f"loose-{num}-{login}"
        groups[rid].append({
            "path": c.get("path"),
            "line": c.get("line") or c.get("original_line"),
            "diff_hunk": (c.get("diff_hunk") or "")[:1500],
            "body": c.get("body", ""),
        })
    # formal review bodies/states for those ids
    reviews = gh.get(f"/repos/{repo}/pulls/{num}/reviews") or []
    rmap = {r["id"]: r for r in reviews
            if (r.get("user") or {}).get("login") == login}
    # also include CHANGES_REQUESTED/long-body reviews with no inline comments
    for r in reviews:
        if (r.get("user") or {}).get("login") != login:
            continue
        if r["id"] not in groups and is_substantive(r.get("body"), r.get("state", "")):
            groups[r["id"]] = []
    units = []
    for rid, cs in groups.items():
        rv = rmap.get(rid, {})
        body, state = rv.get("body", ""), rv.get("state", "")
        if not (is_substantive_unit(cs) or is_substantive(body, state)):
            continue
        sc = sum(comment_score(c["body"]) for c in cs) + (4 if state == "CHANGES_REQUESTED" else 0)
        units.append({"repo": repo, "pr": num, "review_id": rid,
                      "comments": cs, "review_body": body, "review_state": state,
                      "submitted_at": rv.get("submitted_at"),
                      "score": round(sc, 2)})
    return units


def is_substantive(body: str | None, state: str) -> bool:
    body = body or ""
    if state == "CHANGES_REQUESTED":
        return True
    return state in ("COMMENTED", "APPROVED") and len(body) >= SEL["min_body_chars"]


def collect():
    gh = GitHub(min_interval=GH_CFG["min_request_interval_s"])
    ranked = load_json(RANKED, [])
    if not ranked:
        print("run discover/rank first"); return
    need = SEL["reviews_per_reviewer"]
    n_reviewers = SEL["num_reviewers"]
    pr_scan = GH_CFG.get("collect_pr_scan", 400)

    existing = load_json(OUT_PATH, {"reviewers": {}})
    dataset = existing.get("reviewers", {})
    chosen = [l for l, b in dataset.items() if len(b.get("reviews", [])) >= need]

    for cand in ranked:
        if len(chosen) >= n_reviewers:
            break
        login = cand["login"]
        have = dataset.get(login, {}).get("reviews", [])
        if len(have) >= need:
            if login not in chosen:
                chosen.append(login)
            continue
        kept = list(have)
        seen = {(r["repo"], r["pr"], r["review_id"]) for r in have}
        # search the repos this reviewer is active in, then any seed repo
        repos = list(dict.fromkeys(cand.get("repos", []) + GH_CFG["seed_repos"]))
        print(f"[collect] {login}: have {len(kept)}, need {need}; "
              f"searching {len(repos)} repos")
        for repo in repos:
            if len(kept) >= need:
                break
            q = f"type:pr repo:{repo} reviewed-by:{login}"
            try:
                prs = gh.paginate("/search/issues",
                                  {"q": q, "sort": "updated", "per_page": 50},
                                  max_items=pr_scan)
                for item in prs:
                    if len(kept) >= need:
                        break
                    num = item["number"]
                    if any(s[0] == repo and s[1] == num for s in seen):
                        continue
                    for unit in _units_for_pr(gh, repo, num, login):
                        key = (unit["repo"], unit["pr"], unit["review_id"])
                        if key in seen:
                            continue
                        rec = _enrich(gh, login, unit)
                        if rec:
                            kept.append(rec); seen.add(key)
                            if len(kept) % 10 == 0:
                                _save(dataset, login, cand, kept)
                                print(f"    {login}: {len(kept)}/{need} "
                                      f"({gh.calls} calls)")
                        if len(kept) >= need:
                            break
            except Exception as e:  # noqa: BLE001
                print(f"    {login} search {repo} error: {e}")
                continue
        dataset[login] = {"meta": cand, "reviews": kept}
        _save(dataset, login, cand, kept)
        if len(kept) >= max(20, need // 5):
            chosen.append(login)
        print(f"[collect] {login}: DONE {len(kept)} reviews")

    meta = {
        "pain_point_target": "10/10",
        "reviews_per_reviewer_target": need,
        "num_reviewers_target": n_reviewers,
        "chosen_reviewers": chosen,
        "selection_config": SEL,
        "seed_repos": GH_CFG["seed_repos"],
    }
    _write_atomic(json.dumps(
        {"meta": meta, "reviewers": {k: dataset[k] for k in dataset}}, indent=2))
    print(f"[collect] wrote {OUT_PATH}: {len(dataset)} reviewers")


def _enrich(gh: GitHub, login: str, unit: dict):
    repo, num, rid = unit["repo"], unit["pr"], unit["review_id"]
    ctx = _pr_context(gh, repo, num)
    if ctx is None:
        return None
    inline = unit.get("comments", [])
    return {
        "repo": repo,
        "pr": num,
        "pr_url": ctx["html_url"],
        "review_id": rid,
        "review_state": unit.get("review_state"),
        "review_submitted_at": unit.get("submitted_at"),
        "review_body": unit.get("review_body", ""),
        "inline_comments": inline,
        "pr_title": ctx["title"],
        "pr_body": ctx["body"],
        "pr_diff": ctx["diff"],
        "pr_files": ctx["files"],
        "pr_stats": {"additions": ctx["additions"],
                     "deletions": ctx["deletions"],
                     "changed_files": ctx["changed_files"]},
        "heuristic_score": unit["score"],
    }


def _write_atomic(text):
    tmp = OUT_PATH.with_name(OUT_PATH.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, OUT_PATH)   # atomic -> concurrent readers never see a torn file


def _save(dataset, login, cand, kept):
    dataset[login] = {"meta": cand, "reviews": kept}
    _write_atomic(json.dumps(
        {"meta": {"partial": True}, "reviewers": dataset}, indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    {"discover": discover, "rank": rank, "collect": collect, "wide": wide,
     "repos": lambda: discover_java_repos(
         GitHub(min_interval=GH_CFG["min_request_interval_s"]),
         GH_CFG.get("wide", {}).get("max_repos", 800)),
     "all": lambda: (discover(), collect())}.get(cmd, lambda: print(__doc__))()
