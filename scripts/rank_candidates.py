"""APA_citation_finder :: rank_candidates.py
Stage 7 — Candidate ranking.

ONLY papers that passed BOTH gates are ranked:
    Gate A: paper verification (VERIFIED / LIKELY_REAL only)
    Gate B: support threshold (default 0.60, High Rigor 0.75)

Ranking profiles (per claim type, spec §31):
    CURRENT_EMPIRICAL: support .40 quality .25 recency .25 diversity .10
    FOUNDATIONAL:      support .40 originality .35 authority .20 recency .05
    METHOD:            support .40 method_authority .35 relevance .20 recency .05
    DEFINITION:        canonical/original-first (originality proxy: year age +
                       citation count), support dominates

Quality (journal tier) is only a signal — support always dominates prestige.
Diversity (same author/journal) is a minor tiebreak, never at the cost of
support.

Output final_papers.json: {"claims": [...], "papers": [...], "links": [
  {claim_id, paper_id, support_score, support_level, evidence_source,
   evidence_text, selection_status, reason}]}
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from utils.ids import paper_id_hash
from utils.jsonl import read_claims, load_json, write_json

PROFILES: dict[str, dict[str, float]] = {
    "CURRENT_EMPIRICAL": {"support": 0.40, "quality": 0.25, "recency": 0.25, "diversity": 0.10},
    "FOUNDATIONAL": {"support": 0.40, "originality": 0.35, "authority": 0.20, "recency": 0.05},
    "METHOD": {"support": 0.40, "method_authority": 0.35, "relevance": 0.20, "recency": 0.05},
    "DEFINITION": {"support": 0.50, "originality": 0.30, "authority": 0.20, "recency": 0.0},
    "DEFAULT": {"support": 0.40, "quality": 0.25, "recency": 0.25, "diversity": 0.10},
}

DEFAULT_SUPPORT_THRESHOLD = 0.60
HIGH_RIGOR_THRESHOLD = 0.75

MAX_PER_CLAIM = {"default": 1, "contested": 2, "systematic": 3}


def profile_for(claim_type: str, citation_need: str) -> dict:
    if claim_type == "DEFINITION":
        return PROFILES["DEFINITION"]
    if claim_type in ("THEORETICAL", "HISTORICAL"):
        return PROFILES["FOUNDATIONAL"]
    if claim_type == "METHOD":
        return PROFILES["METHOD"]
    return PROFILES["CURRENT_EMPIRICAL"]


def originality_score(paper: dict, current_year: int | None = None) -> float:
    """Older seminal papers > newer papers for FOUNDATIONAL profiles."""
    import datetime
    if current_year is None:
        current_year = datetime.datetime.now().year
    year = paper.get("year")
    if not year:
        return 0.5
    age = current_year - year
    if age >= 20:
        return 1.0
    if age >= 10:
        return 0.8
    if age >= 5:
        return 0.5
    return 0.3


def authority_score(paper: dict) -> float:
    """citation_count normalized (log scale, capped)."""
    cites = paper.get("citation_count") or 0
    if cites <= 0:
        return 0.1
    import math
    return round(min(1.0, math.log10(cites + 1) / 4.0), 4)


def method_authority_score(paper: dict) -> float:
    """Method papers: authority from citations + conference/journal tier."""
    return round(authority_score(paper) * 0.7 + (paper.get("tier_score") or 0.1) * 0.3, 4)


def diversity_score(paper: dict, selected: list[dict]) -> float:
    """Penalize if the paper's first author or venue already selected."""
    if not selected:
        return 1.0
    authors = paper.get("authors") or []
    first = authors[0].lower() if authors else ""
    venue = (paper.get("venue") or "").lower()
    for s in selected:
        s_authors = s.get("authors") or []
        s_first = s_authors[0].lower() if s_authors else ""
        s_venue = (s.get("venue") or "").lower()
        if first and s_first and first == s_first:
            return 0.6
        if venue and s_venue and venue == s_venue:
            return 0.7
    return 1.0


def composite(paper: dict, profile: dict, selected: list[dict]) -> float:
    support = paper.get("support_score") or 0.0
    quality = paper.get("tier_score") or 0.1
    recency = paper.get("recency_score") or 0.1
    orig = originality_score(paper)
    authority = authority_score(paper)
    m_authority = method_authority_score(paper)
    div = diversity_score(paper, selected)

    score = (
        support * profile.get("support", 0.40) +
        quality * profile.get("quality", 0.0) +
        recency * profile.get("recency", 0.0) +
        orig * profile.get("originality", 0.0) +
        authority * profile.get("authority", 0.0) +
        m_authority * profile.get("method_authority", 0.0) +
        div * profile.get("diversity", 0.0)
    )
    return round(score, 4)



def rank_for_claim(
    papers: list[dict],
    claim: dict,
    threshold: float = DEFAULT_SUPPORT_THRESHOLD,
    per_claim: int = 1,
) -> tuple[list[dict], list[dict]]:
    """Returns (selected, rejected). Selected papers satisfy:
    verification gate (already applied upstream) AND support threshold.
    """
    selected: list[dict] = []
    rejected: list[dict] = []

    candidates = []
    for p in papers:
        score = p.get("support_score") or 0.0
        if score < threshold:
            rejected.append(p)
            continue
        if p.get("verification_status") not in ("VERIFIED", "LIKELY_REAL"):
            rejected.append(p)
            continue
        # hard gate: contradictory / insufficient evidence can never be
        # rescued by ranking, regardless of the numeric score
        if p.get("support_level") in ("CONTRADICTORY", "INSUFFICIENT_EVIDENCE"):
            rejected.append(p)
            continue
        candidates.append(p)

    profile = profile_for(claim.get("claim_type", ""), claim.get("citation_need", ""))
    remaining = list(candidates)
    while remaining and len(selected) < per_claim:
        # re-sort with the *current* selected set so diversity can differ
        remaining.sort(key=lambda p: composite(p, profile, list(selected)), reverse=True)
        best = remaining.pop(0)
        selected.append(best)
    rejected.extend(remaining)
    return selected, rejected


def composite_score(paper: dict, profile: dict, selected: list[dict]) -> float:
    return composite(paper, profile, selected)


def rank_all(
    claims: list[dict],
    claim_papers: dict[str, list[dict]],
    threshold: float = DEFAULT_SUPPORT_THRESHOLD,
) -> dict:
    """claims: list of claim dicts; claim_papers: {claim_id: [papers...]}."""
    links: list[dict] = []
    all_selected: list[dict] = []
    all_rejected: list[dict] = []

    for claim in claims:
        cid = claim.get("claim_id", "")
        papers = claim_papers.get(cid, [])
        if not papers:
            continue
        need = claim.get("citation_need", "")
        per_claim = MAX_PER_CLAIM.get(
            "contested" if need == "REQUIRED" else "default", 1)
        # systematic statements get up to 3
        if need == "REQUIRED" and claim.get("claim_type") == "CURRENT_STATE":
            per_claim = 3
        selected, rejected = rank_for_claim(papers, claim, threshold, per_claim)
        for p in selected:
            links.append({
                "claim_id": cid,
                "paper_id": paper_id_hash(p),
                "title": p.get("title"),
                "doi": p.get("doi"),
                "support_score": p.get("support_score"),
                "support_level": p.get("support_level"),
                "evidence_level": p.get("evidence_level"),
                "evidence_source": p.get("evidence_source"),
                "evidence_text": (p.get("evidence_text") or "")[:1000],
                "selection_status": "SELECTED",
                "reason": p.get("support_reasoning", ""),
            })
            all_selected.append(p)
        for p in rejected:
            all_rejected.append(p)

    # dedupe selected papers across claims
    seen: set[str] = set()
    unique_selected = []
    for p in all_selected:
        pid = paper_id_hash(p)
        if pid not in seen:
            seen.add(pid)
            unique_selected.append(p)
    return {
        "claims": claims,
        "papers": unique_selected,
        "rejected": all_rejected,
        "links": links,
    }


def _cli() -> int:
    p = argparse.ArgumentParser(description="Rank claim-paper candidates")
    p.add_argument("--claims", required=True, help="claims.json")
    p.add_argument("--candidates-dir", required=True,
                   help="dir with claim_<id>.json files")
    p.add_argument("--threshold", type=float, default=DEFAULT_SUPPORT_THRESHOLD)
    p.add_argument("--output", "-o", default="final_papers.json")
    args = p.parse_args()

    import json as _json
    from pathlib import Path

    claims = read_claims(args.claims)
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    claim_papers: dict[str, list[dict]] = {}
    cdir = Path(args.candidates_dir)
    for c in claims:
        cid = c.get("claim_id", "")
        f = cdir / f"claim_{cid}.json"
        if f.exists():
            claim_papers[cid] = _json.loads(f.read_text(encoding="utf-8"))

    result = rank_all(claims, claim_papers, args.threshold)
    write_json(args.output, result)
    print(f"Ranked: {len(result['papers'])} selected papers, "
          f"{len(result['links'])} claim links → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
