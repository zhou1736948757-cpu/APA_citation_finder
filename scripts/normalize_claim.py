"""APA_citation_finder :: normalize_claim.py
Stage 1d — Claim normalization.

Produces for every claim:
    normalized_claim   (English searchable form; Chinese originals are kept
                        verbatim in original_text and mapped here by the
                        agent/LLM when a translation is provided)
    search_concepts[]  (core concepts)
    synonyms[]         (plausible search synonyms)
    population / context / outcome / time / geography (optional facets)

Rules:
  * original_claim is NEVER modified or replaced by the normalized form.
  * The query is a search artifact; support evaluation always targets the
    ORIGINAL (or normalized) claim, never the raw query.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from utils.jsonl import read_claims, write_claims, write_json, load_json
from utils.text import extract_keywords, is_chinese

_SYNONYM_MAP = {
    "generative ai": ["large language models", "chatgpt", "generative artificial intelligence", "llms"],
    "llm": ["large language model", "generative ai", "chatgpt"],
    "critical thinking": ["higher-order thinking", "analytical thinking", "critical reasoning"],
    "students": ["university students", "college students", "undergraduates", "higher education students"],
    "over-reliance": ["overreliance", "dependence", "uncritical reliance", "overdependence"],
    "e-learning": ["online learning", "digital learning", "distance education"],
    "acceptance": ["adoption", "usage intention", "behavioral intention"],
    "technology acceptance": ["technology adoption", "technology use"],
    "fraud": ["fraud detection", "financial fraud"],
    "deep learning": ["neural networks", "deep neural networks"],
}

_ZH_KEYWORD_MAP = {
    "生成式人工智能": "generative artificial intelligence",
    "人工智能": "artificial intelligence",
    "大语言模型": "large language model",
    "学生": "students",
    "学习": "learning",
    "学习效果": "learning outcomes",
    "教育": "education",
    "教师": "teachers",
    "提升": "improve",
    "提高": "improve",
    "显著": "significantly",
    "影响": "impact",
    "效果": "effect",
    "研究": "research",
    "研究表明": "research shows",
    "框架": "framework",
    "模型": "model",
    "算法": "algorithm",
    "方法": "method",
    "理论": "theory",
    "技术": "technology",
    "接受": "acceptance",
    "行为意向": "behavioral intention",
    "绩效": "performance",
    "创新": "innovation",
    "采用": "adoption",
    "信任": "trust",
    "隐私": "privacy",
    "风险": "risk",
    "证据": "evidence",
    "结论": "conclusion",
    "有效性": "effectiveness",
    "效率": "efficiency",
    "动机": "motivation",
    "满意度": "satisfaction",
}


_FACET_HINTS = {
    "population": r"\b(students|teachers|employees|patients|children|adults|consumers|users|"
                  r"university|college|hospital|firms|companies|smes|organizations)\w*",
    "geography": r"\b(China|US|USA|United States|UK|Europe|Germany|Japan|Korea|India|Australia|"
                 r"Africa|developing countries)\b",
    "time": r"\b(202[0-9]|201[0-9]|recent years|since 20\d{2})\b",
}


def normalize_claim(claim_text: str, normalized_hint: str | None = None) -> dict:
    """Return {normalized_claim, search_concepts, synonyms, facets}."""
    original = claim_text.strip()
    normalized = normalized_hint.strip() if normalized_hint and normalized_hint.strip() else original

    concepts: list[str] = []
    synonyms: list[str] = []
    low_norm = normalized.lower()

    # Chinese claims: map known terms to English search concepts
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in original)
    if has_cjk:
        for zh, en in _ZH_KEYWORD_MAP.items():
            if zh in original:
                if en not in concepts:
                    concepts.append(en)
                if en not in synonyms:
                    synonyms.append(en)

    # noun-phrase concepts via keywords
    for kw in extract_keywords(normalized, top_n=6):
        if kw not in concepts:
            concepts.append(kw)
        for src, alts in _SYNONYM_MAP.items():
            if src in low_norm:
                for alt in alts:
                    if alt not in synonyms:
                        synonyms.append(alt)

    # direct synonym substitution for known phrases → also search concepts
    for src, alts in _SYNONYM_MAP.items():
        if src in low_norm:
            for alt in alts:
                if alt not in concepts and len(alt.split()) <= 4:
                    concepts.append(alt)
                    synonyms.append(alt)

    facets: dict[str, str] = {}
    for facet, pat in _FACET_HINTS.items():
        m = re.search(pat, normalized, re.I)
        if m:
            facets[facet] = m.group(0).lower()

    return {
        "normalized_claim": normalized,
        "search_concepts": concepts[:8],
        "synonyms": synonyms[:8],
        "population": facets.get("population", ""),
        "context": "",
        "outcome": "",
        "time": facets.get("time", ""),
        "geography": facets.get("geography", ""),
    }


def process(claims: list[dict], hint_file: str | None = None) -> list[dict]:
    hints: dict[str, str] = {}
    if hint_file:
        try:
            hints = load_json(hint_file)
        except Exception:
            hints = {}
    for c in claims:
        cid = c.get("claim_id", "")
        norm = normalize_claim(c.get("original_text") or "", hints.get(cid))
        c.update(norm)
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize claims")
    parser.add_argument("--input", default="claims.json")
    parser.add_argument("--output", default=None)
    parser.add_argument("--hints", default=None,
                        help="JSON {claim_id: english_normalized_text} for Chinese claims")
    args = parser.parse_args()

    claims = read_claims(args.input)
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    claims = process(claims, args.hints)
    target = args.output or args.input
    write_claims(target, claims)
    print(f"Normalized {len(claims)} claims → {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
