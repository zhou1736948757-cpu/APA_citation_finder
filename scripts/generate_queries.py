"""APA_citation_finder :: generate_queries.py
Stage 1e — Multi-query generation per claim.

Every claim gets at least:
    broad      — core concepts only (high recall)
    precise    — the normalized claim (exact phrasing, <= 30 words)
    synonym    — concepts replaced by synonyms
    domain     — concepts + domain context

Plus type-driven queries:
    authoritative      — "systematic review / meta-analysis" flavour (EMPIRICAL)
    foundational       — "seminal", "original theory" (THEORETICAL/DEFINITION)
    method             — method name (METHOD)

Queries are search artifacts; the support evaluation always targets the
original/normalized claim (see IRON RULE: query != claim).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from utils.jsonl import read_claims, write_claims, write_json, load_json

MAX_QUERY_WORDS = 30


def _truncate(q: str) -> str:
    words = q.split()
    if len(words) <= MAX_QUERY_WORDS:
        return q
    return " ".join(words[:MAX_QUERY_WORDS])


def _strip_hedges(claim: str) -> str:
    """Remove weak qualifiers for the broad query (never for the claim)."""
    return re.sub(r"\b(may|might|possibly|perhaps|often|typically|generally|seem(s)?)\b",
                  "", claim, flags=re.I).strip()


def generate_queries(claim: dict | str) -> list[dict]:
    if isinstance(claim, str):
        from normalize_claim import normalize_claim
        norm = normalize_claim(claim)
        claim = {"original_text": claim, "normalized_claim": norm["normalized_claim"],
                 "search_concepts": norm["search_concepts"], "synonyms": norm["synonyms"]}
    norm = claim.get("normalized_claim") or claim.get("original_text") or ""
    concepts = claim.get("search_concepts") or []
    synonyms = claim.get("synonyms") or []
    ctype = claim.get("claim_type", "")

    queries: list[dict] = []

    # precise — the normalized claim itself
    precise = _truncate(norm)
    queries.append({"type": "precise", "query": precise})
    norm_query = norm

    # broad — concepts only
    if concepts:
        broad = _truncate(" ".join(concepts[:6]))
        if broad and broad.lower() != precise.lower():
            queries.append({"type": "broad", "query": broad})

    # synonym — replace exactly ONE concept with its synonym, keeping the
    # rest of the sentence intact (one swap, not a global mangling)
    if synonyms and concepts:
        syn_query = norm
        swapped = False
        for conc in concepts:
            if swapped:
                break
            if not conc or conc.lower() not in norm.lower():
                continue
            for alt in synonyms:
                if alt.lower() == conc.lower() or len(alt.split()) < 2:
                    continue
                if alt.lower() in norm.lower():
                    continue
                syn_query = re.sub(rf"\b{re.escape(conc)}\b", alt, norm,
                                   count=1, flags=re.I)
                swapped = True
                break
        syn_query = _truncate(syn_query)
        if syn_query.lower() not in {q["query"].lower() for q in queries}:
            queries.append({"type": "synonym", "query": syn_query})

    # domain — concept + domain hint (falls back to the strongest synonym so
    # every claim still gets a domain query)
    domain_words = []
    if claim.get("population"):
        domain_words.append(claim["population"])
    if claim.get("context"):
        domain_words.append(claim["context"])
    if concepts:
        base = " ".join(concepts[:3])
        if domain_words:
            base = base + " " + " ".join(domain_words[:2])
        elif synonyms:
            base = base + " " + synonyms[0]
        dq = _truncate(base)
        if dq.lower() not in {q["query"].lower() for q in queries}:
            queries.append({"type": "domain", "query": dq})

    # type-specific queries
    if ctype in ("EMPIRICAL", "CURRENT_STATE"):
        aq = _truncate(norm + " systematic review")
        if aq.lower() not in {q["query"].lower() for q in queries}:
            queries.append({"type": "authoritative", "query": aq})
    elif ctype in ("THEORETICAL", "DEFINITION"):
        fq = _truncate(norm + " theory")
        if fq.lower() not in {q["query"].lower() for q in queries}:
            queries.append({"type": "foundational", "query": fq})
    elif ctype == "METHOD":
        mq = _truncate(norm + " method")
        if mq.lower() not in {q["query"].lower() for q in queries}:
            queries.append({"type": "foundational", "query": mq})

    return queries


def process(claims: list[dict]) -> list[dict]:
    for c in claims:
        if not c.get("queries"):
            c["queries"] = generate_queries(c)
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate search queries per claim")
    parser.add_argument("--input", default="claims.json")
    parser.add_argument("--output", default=None)
    parser.add_argument("--output-dir", default=None,
                        help="write claim_<id>.json per claim (with queries)")
    args = parser.parse_args()

    claims = read_claims(args.input)
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    claims = process(claims)
    if args.output_dir:
        from pathlib import Path as _P
        out_dir = _P(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for c in claims:
            write_claims(str(out_dir / f"claim_{c.get('claim_id', 'x')}.json"), [c])
        target = str(out_dir)
    else:
        target = args.output or args.input
        write_claims(target, claims)
    total = sum(len(c.get("queries") or []) for c in claims)
    print(f"Generated {total} queries for {len(claims)} claims → {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
