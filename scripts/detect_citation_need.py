"""APA_citation_finder :: detect_citation_need.py
Stage 1b — Citation need detection for each claim.

Classifies every claim as:
    REQUIRED     — empirical findings, statistics, historical facts,
                   theoretical definitions, contested claims, causal claims,
                   specific scientific claims, named methodological thresholds
    RECOMMENDED  — background statements that benefit from a citation
    OPTIONAL     — context; citation acceptable but not expected
    NOT_NEEDED   — author's own data/methods/transitions; do not cite

NOT_NEEDED claims are KEPT in claims.json (marked) for auditability but never
searched. The classifier is heuristic; the agent (per SKILL.md) may override
any verdict with justification when reviewing candidates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from utils.jsonl import read_claims, write_claims, write_json, load_json

# ---- REQUIRED signal patterns ------------------------------------------
_REQUIRED_RE = [
    re.compile(r"\d+\.?\d*\s?%"),
    re.compile(r"\$(?:\d|X)"),
    re.compile(r"(increased|decreased|reduced|improved|raised|lowered)\s+by\b", re.I),
    re.compile(r"(accuracy|performance|efficiency|effectiveness|reliability|prevalence|incidence)\s+of\b", re.I),
    re.compile(r"has been (shown|proven|demonstrated|established|found|reported)\b", re.I),
    re.compile(r"it is (well known|widely accepted|generally believed|well established|commonly understood)", re.I),
    re.compile(r"(according to|based on|following)\s+(the|a|prior|previous|recent|seminal)", re.I),
    re.compile(r"(first proposed|introduced by|developed by|demonstrated in|defined by|coined)", re.I),
    re.compile(r"(outperform|surpass|exceed|outperforms|surpasses)", re.I),
    re.compile(r"(state-of-the-art|state of the art|cutting-edge|SOTA)", re.I),
    re.compile(r"(evidence|empirical|experimental|theoretical)\s+(shows|suggests|indicates|demonstrates|supports|confirms)", re.I),
    re.compile(r"\bcauses?\b|\bleads to\b|\bresults in\b|\bcorrelates? with\b|\bis associated with\b", re.I),
    re.compile(r"(was|were|is|are)\s+(found|shown|observed|estimated)\s+to\b", re.I),
    re.compile(r"according to [A-Z][a-z]+", re.I),
    re.compile(r"\((?:19|20)\d{2}[a-z]?\)"),
    re.compile(r"\[(?:19|20)\d{2}\]"),
    re.compile(r"\b(mean|median|average|p\s*[<=>]\s*0\.\d|statistically significant)\b", re.I),
]
# ---- NOT_NEEDED patterns ----------------------------------------------
_NOT_NEEDED_RE = [
    re.compile(r"^(in this paper|in this work|in this study|in this article|in this section|"
               r"we (propose|present|introduce|show|demonstrate|develop|design|collect|observe|found|found that))", re.I),
    re.compile(r"^(本文|本研究|我们|笔者)(提出|认为|主张|介绍|采用|使用|设计了|构建了|收集了|观察到)"),
    re.compile(r"^(the remainder of|the rest of|the next section|the following section|"
        r"section \d|chapter \d|table \d|figure \d|algorithm \d|equation \d)", re.I),
    re.compile(r"^(we|our) (data|results|findings|survey|questionnaire|responses|sample|participants)\b", re.I),
    re.compile(r"\b(as follows|below|above|here)\b", re.I),
]
# ---- RECOMMENDED patterns ----------------------------------------------
_RECOMMENDED_RE = [
    re.compile(r"(is widely used|commonly used|frequently employed|increasingly (used|adopted|common))", re.I),
    re.compile(r"(previous|prior|existing|recent|earlier|more recent)\s+(work|study|studies|research|literature|efforts|reviews)", re.I),
    re.compile(r"(a growing body|a large body|substantial evidence|mounting evidence)", re.I),
]


def classify_need(claim_text: str) -> str:
    t = claim_text.strip()
    low = t.lower()
    for pat in _NOT_NEEDED_RE:
        if pat.search(t) or pat.search(low):
            return "NOT_NEEDED"
    for pat in _REQUIRED_RE:
        if pat.search(t) or pat.search(low):
            return "REQUIRED"
    for pat in _RECOMMENDED_RE:
        if pat.search(t) or pat.search(low):
            return "RECOMMENDED"
    # generic descriptive statement about the world → RECOMMENDED
    return "RECOMMENDED"


def process(claims: list[dict]) -> list[dict]:
    for c in claims:
        if not c.get("citation_need"):
            c["citation_need"] = classify_need(c.get("original_text") or "")
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect citation need for claims")
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
        counts[c.get("citation_need", "")] = counts.get(c.get("citation_need", ""), 0) + 1
    print(f"Citation need: {counts} → {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
