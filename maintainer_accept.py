#!/usr/bin/env python3
"""maintainer_accept.py — predict P(a maintainer merges an unsolicited external PR) for a repo, and the
REPUTATIONAL RISK of trying. A pre-screen for the PR campaign: spend effort where merges happen and the
downside is low, skip the barren and the dangerous.

The taxonomy this encodes (from the mutation-testing sandbox's field results):
  - Foundations / true multi-maintainer projects (Apache, Eclipse, DSpace, dkpro): ~75% merge, zero
    hostility, institutional process. THE SWEET SPOT.
  - Solo maintainers: a coin-flip on merge, AND the source of every public shaming. Bus-factor ~= 1 is
    where the "AFK fish-farm" fights happen. High reputational risk.
  - Enterprises (AWS, Liquibase): safe but barren — polite silence, near-zero external-merge yield.
    Low value to target.

So the decision is TWO-axis: merge yield x reputational risk. We output P(merge), a risk flag, and a
recommendation (TARGET / CAUTION / SKIP). The strongest single empirical signal is the number of DISTINCT
recent PR-mergers (the bus factor of the review process) and the external-PR merge rate — those dominate;
the owner-type label is only a prior.

Usage:
  python3 maintainer_accept.py apache/shardingsphere
  python3 maintainer_accept.py owner/repo --json
Needs `gh` authenticated (uses `gh api`).
"""
from __future__ import annotations
import json
import subprocess
import sys

# Curated priors. These only nudge the score; the empirical signals (distinct mergers, external merge
# rate) carry most of the weight, so a mislabel here is recoverable from the data.
FOUNDATIONS = {
    "apache", "eclipse", "eclipse-ee4j", "dspace", "dkpro", "jenkinsci", "spring-projects",
    "quarkusio", "finos", "openjdk", "junit-team", "googleapis", "cncf", "knative", "fabric8io",
    "resilience4j", "micrometer-metrics", "reactor", "reactivex",
}
# Enterprise orgs that are typically BARREN for unsolicited external PRs (polite silence). NOT every
# company: Alibaba/Google OSS merge readily, so they are NOT here — the empirical yield will separate them.
ENTERPRISES = {
    "aws", "awslabs", "amazon-archives", "liquibase", "datastax", "zendesk", "opensearch-project",
    "microsoft", "azure", "netflix", "salesforce", "hashicorp", "elastic", "confluentinc",
}


def gh(path: str):
    """GET a gh api path, return parsed JSON or None. Never raises."""
    try:
        r = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                           capture_output=True, text=True, timeout=40)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return None


def _ext(assoc: str) -> bool:
    """Is this PR author an EXTERNAL contributor (not a member/owner)? Those are the PRs that test the
    'will they merge a stranger' question — a MEMBER's own merged PR says nothing about external yield."""
    return str(assoc).upper() in ("CONTRIBUTOR", "NONE", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR", "MANNEQUIN")


def features(owner: str, repo: str) -> dict:
    f = {"owner": owner, "repo": repo}
    who = gh(f"users/{owner}") or {}
    f["owner_type"] = who.get("type", "Unknown")  # User | Organization
    f["is_org"] = f["owner_type"] == "Organization"

    # contributor concentration (cheap all-time proxy for bus factor)
    contrib = gh(f"repos/{owner}/{repo}/contributors?per_page=30&anon=false") or []
    counts = sorted((c.get("contributions", 0) for c in contrib if isinstance(c, dict)), reverse=True)
    total = sum(counts) or 1
    f["n_contributors"] = sum(1 for c in counts if c >= 2)
    f["top1_share"] = round(counts[0] / total, 3) if counts else 1.0
    f["top2_share"] = round(sum(counts[:2]) / total, 3) if counts else 1.0

    # external merge yield: of recent closed PRs by EXTERNAL authors, the fraction that got merged. The
    # /pulls list does not populate merged_by, so we measure yield (merged_at) not who-merged here.
    pulls = gh(f"repos/{owner}/{repo}/pulls?state=closed&per_page=50&sort=updated&direction=desc") or []
    ext_total, ext_merged = 0, 0
    for p in pulls:
        if not isinstance(p, dict):
            continue
        if _ext(p.get("author_association", "")):
            ext_total += 1
            if p.get("merged_at"):
                ext_merged += 1
    f["external_pr_sample"] = ext_total
    f["external_merge_rate"] = round(ext_merged / ext_total, 3) if ext_total else None

    # bus factor of who WRITES the code: distinct committers + top committer's share over the last ~100
    # commits (reliable, one call — unlike merged_by which the list endpoint omits). A foundation has many
    # distinct committers; a bus-factor~=1 solo is one person doing ~everything.
    from collections import Counter
    commits = gh(f"repos/{owner}/{repo}/commits?per_page=100") or []
    authors = []
    for c in commits:
        if not isinstance(c, dict):
            continue
        a = (c.get("author") or {}).get("login") or ((c.get("commit") or {}).get("author") or {}).get("name")
        if a:
            authors.append(a)
    cc = Counter(authors)
    f["commit_sample"] = len(authors)
    f["distinct_committers"] = len(cc)
    f["top_committer_share"] = round(cc.most_common(1)[0][1] / len(authors), 3) if authors else 1.0

    # OPPORTUNITY to have grown a team: a popular, old, much-forked repo with many would-be contributors has
    # had every chance to onboard co-maintainers. Realized-team measured above; the GAP is the signal (P18).
    meta = gh(f"repos/{owner}/{repo}") or {}
    f["stars"] = meta.get("stargazers_count", 0)
    f["forks"] = meta.get("forks_count", 0)
    import datetime as _dt
    try:
        created = _dt.datetime.fromisoformat(str(meta.get("created_at", "")).replace("Z", "+00:00"))
        f["age_years"] = round((_dt.datetime.now(_dt.timezone.utc) - created).days / 365.25, 1)
    except Exception:  # noqa: BLE001
        f["age_years"] = 0.0
    ext_authors = {(p.get("user") or {}).get("login") for p in pulls
                   if isinstance(p, dict) and _ext(p.get("author_association", ""))}
    f["distinct_external_authors"] = len({a for a in ext_authors if a})

    # process signal (institutional = foundation-like)
    f["has_contributing"] = gh(f"repos/{owner}/{repo}/contents/CONTRIBUTING.md") is not None
    return f


def classify(f: dict) -> str:
    o = f["owner"].lower()
    if o in FOUNDATIONS:
        return "foundation"
    if o in ENTERPRISES:
        return "enterprise"
    # data-driven: an org with a broad committer base (>=6 distinct, no single dominant author) behaves
    # like a foundation regardless of label.
    if f["is_org"] and f["distinct_committers"] >= 6 and f["top_committer_share"] < 0.5:
        return "foundation-like"
    if (not f["is_org"]) or f["distinct_committers"] <= 2 or f["top_committer_share"] >= 0.6:
        return "solo"
    return "small-team"


def score(f: dict) -> dict:
    cat = classify(f)
    # base merge prior by category (anchored to the field rates)
    base = {"foundation": 0.72, "foundation-like": 0.62, "small-team": 0.5,
            "solo": 0.45, "enterprise": 0.15}[cat]
    # blend with the DIRECT external-merge-rate evidence when we have a real sample (it dominates)
    emr, n = f["external_merge_rate"], f["external_pr_sample"]
    if emr is not None and n >= 5:
        w = min(0.7, n / 50.0 + 0.3)          # more external PRs seen -> trust the evidence more
        p_merge = (1 - w) * base + w * emr
    else:
        p_merge = base
    # a broad committer base lifts merge odds; a one-person bottleneck drags it
    if f["distinct_committers"] >= 8 and f["top_committer_share"] < 0.4:
        p_merge = min(0.9, p_merge + 0.05)
    elif f["distinct_committers"] <= 2 or f["top_committer_share"] >= 0.6:
        p_merge = max(0.1, p_merge - 0.1)

    # --- the OPPORTUNITY GAP (P18's core theory): single-maintainer is ENDOGENOUS ---------------------
    # A solo maintainer of a popular, old, heavily-forked repo with many would-be contributors is solo by
    # REVEALED PREFERENCE (kept sole merge authority), not for lack of a partner. That gatekeeper disposition
    # is what rejects/shames a stranger's PR. A small/young solo is solo by circumstance and often merges
    # gladly. So split solos by the GAP between the opportunity to grow a team and the realized team.
    is_solo = (not f["is_org"]) or f["distinct_committers"] <= 2 or f["top_committer_share"] >= 0.6
    opportunity = (int(f.get("stars", 0) >= 1500) + int(f.get("age_years", 0) >= 4)
                   + int(f.get("distinct_external_authors", 0) >= 12) + int(f.get("forks", 0) >= 300))
    deliberate_solo = is_solo and opportunity >= 2     # had every chance to grow a team, stayed solo
    incidental_solo = is_solo and opportunity <= 1     # small/young: solo by circumstance, often grateful
    # NB: the opportunity gap does NOT move P(merge). Our 200-PR backtest found deliberate and incidental
    # solos merge at the SAME coin-flip rate (~50%) — a red->green-verified PR gets merged even by a
    # gatekeeper. The gap predicts the SHAMING TAIL (the reputational-risk axis, per the field data that
    # solos are the source of every public shaming), so it risk-adjusts SELECTION, not the merge estimate.

    # reputational risk: the deliberate gatekeeper is where the public shamings happen
    if cat in ("foundation", "foundation-like") and not deliberate_solo:
        risk = "low"
    elif deliberate_solo:
        risk = "high"
    elif is_solo:
        risk = "medium"
    else:
        risk = "low"

    # two-axis recommendation: yield x risk. SKIP only the truly barren (enterprise silence / ~0 external
    # yield); the deliberate gatekeeper is CAUTION-high-risk, not SKIP, because some (redisson, jadx) DO
    # merge — the operator decides if the shaming downside is worth it for an impeccable PR.
    if cat == "enterprise" or (emr is not None and n >= 6 and emr < 0.12):
        rec, why = "SKIP", "barren: external PRs almost never merged (polite silence)"
    elif p_merge >= 0.55 and risk == "low":
        rec, why = "TARGET", "multi-maintainer / foundation: high merge yield, low hostility risk"
    elif deliberate_solo:
        rec, why = "CAUTION", "deliberate gatekeeper: popular/old yet still single-maintainer (solo by choice) - merges happen but shaming risk is real; only an impeccable PR"
    elif incidental_solo and (emr or 0) >= 0.5:
        rec, why = "CAUTION", "incidental solo (small/young, decent yield, low downside): worth one clean, well-scoped PR"
    else:
        rec, why = "CAUTION", "mixed signals: proceed selectively with a high-quality, well-scoped PR"

    # selection score (P18): RISK-ADJUSTED expected payoff = P(merge) x reach x risk_factor; SKIP zeroes it.
    # P(merge) is the honest yield; the risk_factor is where the opportunity gap bites — a deliberate
    # gatekeeper with a normal merge rate is still discounted for its shaming tail.
    import math
    reach = max(0.3, min(1.0, math.log10(f.get("stars", 0) + 10) / 4.0))
    risk_factor = {"low": 1.0, "medium": 0.85, "high": 0.65}[risk]
    sel = 0.0 if rec == "SKIP" else round(p_merge * reach * risk_factor, 3)

    return {"category": cat, "p_merge": round(p_merge, 3), "reputational_risk": risk,
            "recommendation": rec, "reason": why, "opportunity": opportunity,
            "deliberate_solo": deliberate_solo, "selection_score": sel}


def predict(owner: str, repo: str) -> dict:
    f = features(owner, repo)
    return {**f, **score(f)}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    as_json = "--json" in sys.argv
    if not args:
        print("usage: maintainer_accept.py owner/repo [--json]"); sys.exit(2)
    owner, repo = args[0].split("/", 1)
    out = predict(owner, repo)
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{owner}/{repo}")
        print(f"  category   : {out['category']}  (owner_type={out['owner_type']}, "
              f"committers={out['distinct_committers']}/top={out['top_committer_share']}, "
              f"external_merge_rate={out['external_merge_rate']} of {out['external_pr_sample']})")
        print(f"  opportunity: {out['opportunity']}/4  (stars={out.get('stars')}, age={out.get('age_years')}y, "
              f"forks={out.get('forks')}, would-be-contributors={out.get('distinct_external_authors')})"
              + ("  [DELIBERATE SOLO]" if out['deliberate_solo'] else ""))
        print(f"  P(merge)   : {out['p_merge']}    selection_score: {out['selection_score']}")
        print(f"  rep. risk  : {out['reputational_risk']}")
        print(f"  >>> {out['recommendation']}: {out['reason']}")
