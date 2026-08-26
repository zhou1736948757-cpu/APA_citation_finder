"""APA_citation_finder :: search_openalex.py
OpenAlex source — semantic discovery, metadata, concepts, citation relations.

Merges: scipilot's inverted-index abstract reconstruction + citation-finder's
venue_type/ISSN/pages parsing. Outputs APA_citation_finder unified paper schema.
"""
from __future__ import annotations

import re
from typing import Any

from utils.http import rate_limited_request
from utils.ids import normalize_doi

OPENALEX_URL = "https://api.openalex.org/works"
POLITE_EMAIL = "scipilot-cite@example.org"
USER_AGENT = "APA_citation_finder/1.0 (mailto:scipilot-cite@example.org)"


def _reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted or not isinstance(inverted, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, pos_list in inverted.items():
        for p in pos_list or []:
            positions.append((p, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _to_unified(item: dict) -> dict:
    doi = normalize_doi(item.get("doi"))
    authors = []
    for au in item.get("authorships", []) or []:
        disp = (au.get("author") or {}).get("display_name") or ""
        if not disp:
            continue
        if "," in disp:  # already "Last, First"
            authors.append(disp.strip())
        else:
            parts = disp.split()
            if len(parts) >= 2:
                authors.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            else:
                authors.append(disp)
    ploc = item.get("primary_location") or {}
    src = ploc.get("source") or {}
    venue = src.get("display_name") or ""
    venue_type = "other"
    oa = item.get("open_access") or {}
    wtype = item.get("type", "")
    if wtype == "article":
        venue_type = "journal"
    elif wtype == "conference-paper":
        venue_type = "conference"
    elif wtype in ("preprint", "posted-content"):
        venue_type = "preprint"
    biblio = item.get("biblio") or {}
    pages = None
    if biblio.get("first_page"):
        pages = f"{biblio['first_page']}-{biblio.get('last_page')}" if biblio.get("last_page") else biblio["first_page"]
    return {
        "title": item.get("title") or item.get("display_name") or "",
        "authors": authors,
        "year": item.get("publication_year"),
        "journal": venue,
        "venue": venue,
        "venue_type": venue_type,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else None,
        "abstract": _reconstruct_abstract(item.get("abstract_inverted_index")),
        "citation_count": item.get("cited_by_count") or 0,
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": pages,
        "publisher": src.get("host_organization_name"),
        "issn_l": src.get("issn_l"),
        "issn": src.get("issn") or [],
        "open_access_pdf": (item.get("open_access") or {}).get("oa_url"),
        "is_oa": oa_status_bool(item.get("open_access") or {}),
        "oa_status": oa.get("oa_status"),
        "language": item.get("language"),
        "keywords": [],
        "source_layer": "api",
        "source": "openalex",
        "source_apis": ["openalex"],
        "tier_score": 0.0,
        "recency_score": 0.0,
        "support_score": None,
        "composite_score": None,
    }


def oa_status_bool(oa: dict) -> bool:
    return bool(oa.get("is_oa", False))


def search_openalex(
    query: str,
    year_range: tuple[int, int] | None = None,
    limit: int = 10,
    mailto: str | None = None,
) -> list[dict]:
    params: dict[str, Any] = {
        "search": query,
        "per_page": min(limit, 50),
        "sort": "relevance_score:desc",
        "mailto": mailto or POLITE_EMAIL,
    }
    filters = ["type:article|conference-paper|preprint|posted-content"]
    if year_range:
        filters.append(f"from_publication_date:{year_range[0]}-01-01,"
                       f"to_publication_date:{year_range[1]}-12-31")
    params["filter"] = ",".join(filters)

    data = rate_limited_request(OPENALEX_URL, params=params,
                                headers={"User-Agent": USER_AGENT}, min_interval=0.5)
    if not data or "results" not in data:
        return []
    return [_to_unified(item) for item in (data.get("results") or [])]


if __name__ == "__main__":
    import argparse
    import json
    import sys
    p = argparse.ArgumentParser(description="OpenAlex search")
    p.add_argument("query")
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()
    yr = (args.from_year, args.to_year) if (args.from_year or args.to_year) else None
    json.dump(search_openalex(args.query, yr, args.limit), sys.stdout, ensure_ascii=False, indent=2)
