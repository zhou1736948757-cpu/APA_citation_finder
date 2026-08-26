"""APA_citation_finder :: search_semantic_scholar.py
Semantic Scholar source — discovery, abstracts, citation context where
available. One of the three core free sources (no API key).
"""
from __future__ import annotations

from utils.ids import normalize_doi
from utils.http import rate_limited_request

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
USER_AGENT = "APA_citation_finder/1.0 (mailto:scipilot-cite@example.org)"


def _to_unified(item: dict) -> dict:
    doi = normalize_doi((item.get("externalIds") or {}).get("DOI"))
    authors = []
    for a in item.get("authors") or []:
        name = a.get("name") or ""
        if name:
            parts = name.split()
            if len(parts) >= 2:
                authors.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            else:
                authors.append(name)
    venue = item.get("venue") or ""
    return {
        "title": item.get("title") or "",
        "authors": authors,
        "year": item.get("year"),
        "journal": venue,
        "venue": venue,
        "venue_type": "journal" if venue and not venue.lower().startswith("arxiv") else "preprint",
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else None,
        "abstract": item.get("abstract") or "",
        "citation_count": item.get("citationCount") or 0,
        "volume": None,
        "issue": None,
        "pages": None,
        "publisher": None,
        "issn_l": None,
        "issn": [],
        "open_access_pdf": None,
        "is_oa": False,
        "oa_status": None,
        "language": None,
        "keywords": [],
        "source_layer": "api",
        "source": "semantic_scholar",
        "source_apis": ["semantic_scholar"],
        "tier_score": 0.0,
        "recency_score": 0.0,
        "support_score": None,
        "composite_score": None,
    }


def search_semantic_scholar(
    query: str,
    year_range: tuple[int, int] | None = None,
    limit: int = 10,
    fields_of_study: list | None = None,
) -> list[dict]:
    params = {
        "query": query,
        "limit": min(limit, 100),
        "fields": "title,authors,year,venue,citationCount,externalIds,abstract,publicationDate",
    }
    if year_range:
        params["year"] = f"{year_range[0]}-{year_range[1]}"
    if fields_of_study:
        params["fieldsOfStudy"] = ",".join(fields_of_study)
    data = rate_limited_request(
        SEMANTIC_SCHOLAR_URL, params=params,
        headers={"User-Agent": USER_AGENT}, min_interval=1.0,
    )
    if not data or "data" not in data:
        return []
    return [_to_unified(item) for item in (data.get("data") or [])]


if __name__ == "__main__":
    import sys
    import json
    import argparse
    p = argparse.ArgumentParser(description="Semantic Scholar search")
    p.add_argument("query")
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()
    yr = (args.from_year, args.to_year) if (args.from_year or args.to_year) else None
    json.dump(search_semantic_scholar(args.query, yr, args.limit), sys.stdout,
              ensure_ascii=False, indent=2)
