"""APA_citation_finder :: classify_claims.py
Stage 1c — Claim type classification.

Types: EMPIRICAL, THEORETICAL, DEFINITION, METHOD, STATISTICAL, HISTORICAL,
       CONTEXTUAL, NORMATIVE, CURRENT_STATE.

Different claim types route to different search strategies and ranking
profiles (see references/claim-types.md and references/scoring.md).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from utils.jsonl import read_claims, write_claims, write_json, load_json

# Strong signal keywords, checked in order of specificity
_SIGNALS: list[tuple[str, list[re.Pattern]]] = [
    ("STATISTICAL", [
        re.compile(r"\d+\.?\d*\s?%"), re.compile(r"\b(mean|median|prevalence|incidence|rate)\b", re.I),
        re.compile(r"p\s*[<=>]\s*0?\.\d"), re.compile(r"correlation|regression|odds ratio|hazard ratio", re.I),
    ]),
    ("DEFINITION", [
        re.compile(r"\bis defined as\b|\bdefined by\b|\brefers to\b|\bis a .*\bconcept\b",
                   re.I), re.compile(r"(UTAUT2|TAM|TOE|theory of planned behavior|definition)", re.I),
        re.compile(r"是一种|指的是|被定义为|是指"),  # Chinese definition markers
    ]),
    ("METHOD", [
        re.compile(r"method|algorithm|framework|approach|technique|procedure|protocol", re.I),
        re.compile(r"we (propose|develop|introduce|present) (a|an|the)", re.I),
        re.compile(r"PLS-SEM|SEM\b|regression|deep learning model|transformer", re.I),
        re.compile(r"算法|方法|流程|步骤|框架(?!理论)"),  # Chinese method markers
    ]),
    ("HISTORICAL", [
        re.compile(r"\bin (19|20)\d{2}\b|\bhistorically\b|\bsince (19|20)\d{2}\b|\bseminal\b",
                   re.I),
    ]),
    ("THEORETICAL", [
        re.compile(r"theory\b|\btheoretical\b|\bconceptual\b|\bframework\b|\bmodel\b|\bparadigm\b", re.I),
    ]),
    ("NORMATIVE", [
        re.compile(r"\bshould\b|\bmust\b|\bought to\b|\betically\b|\bnormative\b|\brequires?\b", re.I),
    ]),
    ("EMPIRICAL", [
        re.compile(r"found|showed|observed|measured|evidence|results suggest|studies show",
                   re.I),
    ]),
    ("CURRENT_STATE", [
        re.compile(r"\b(currently|now|today|recent years|increasingly)\b", re.I),
    ]),
]

# Fallback
_DEFAULT_TYPE = "EMPIRICAL"


def classify_type(text: str) -> str:
    t = text or ""
    low = t.lower()
    # stats first (numbers dominate)
    for cls, pats in _SIGNALS:
        if any(p.search(t) or p.search(low) for p in pats):
            return cls
    # empirical indicators like "is associated with" / causal language
    if re.search(r"\b(associated with|leads to|causes|improves|reduces|increases|affects)\b", low):
        return "EMPIRICAL"
    return _DEFAULT_TYPE


def process(claims: list[dict]) -> list[dict]:
    for c in claims:
        if not c.get("claim_type"):
            c["claim_type"] = classify_type(c.get("original_text") or "")
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify claim types")
    parser.add_argument("--input", default="claims.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    claims = read_claims(args.input)
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    claims = process(claims)
    target = args.output or args.input
    write_claims(target, claims)
    counts: dict[str, int] = {}
    for c in claims:
        counts[c.get("claim_type", "")] = counts.get(c.get("claim_type", ""), 0) + 1
    print(f"Claim types: {counts} → {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
