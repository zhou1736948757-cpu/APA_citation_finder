"""APA_citation_finder :: search_crossref.py
Crossref source — DOI/metadata normalization, journal/year/author verification.

Crossref is NOT the primary semantic search engine: its main role in APA_citation_finder
is DOI verification (verify_papers.py) and metadata normalization. Search is
still supported as a fallback source.
"""
from __future__ import annotations

import re

from utils.http import rate_limited_request
from utils.ids import normalize_doi

CROSSREF_URL = "https://api.crossref.org/works"
POLITE_EMAIL = "scipilot-cite@example.org"
USER_AGENT = "APA_citation_finder/1.0 (mailto:scipilot-cite@example.org)"


def _strip_jats(abstract: str) -> str:
    if not abstract:
        return ""
    return re.sub(r"</?jats:[^>]*>", "", abstract).strip()


def _year_of(msg: dict) -> int | None:
    for key in ("issued", "published-print", "published-online", "published"):
        dp = (msg.get(key) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            return int(dp[0][0])
    return None


def _to_unified(item: dict) -> dict:
    doi = normalize_doi(item.get("DOI"))
    title_list = item.get("title") or []
    title = title_list[0] if title_list else ""
    authors = []
    for a in item.get("author") or []:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{family}, {given}".strip(", ")
        if name:
            authors.append(name)
    venue_list = item.get("container-title") or []
    venue = venue_list[0] if venue_list else ""
    cr_type = item.get("type", "")
    venue_type = "journal" if cr_type == "journal-article" else (
        "conference" if cr_type in ("proceedings-article", "proceedings") else
        "book" if cr_type == "book-chapter" else "other")
    year = _year_of(item)
    abstract = _strip_jats(item.get("abstract", "") or "")
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": venue,
        "venue": venue,
        "venue_type": venue_type,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else None,
        "abstract": abstract,
        "citation_count": item.get("is-referenced-by-count") or 0,
        "volume": item.get("volume"),
        "issue": item.get("issue"),
        "pages": item.get("page"),
        "publisher": item.get("publisher"),
        "issn_l": None,
        "issn": item.get("ISSN") or [],
        "open_access_pdf": None,
        "is_oa": False,
        "oa_status": None,
        "language": item.get("language"),
        "keywords": item.get("subject") or [],
        "source_layer": "api",
        "source": "crossref",
        "source_apis": ["crossref"],
        "tier_score": 0.0,
        "recency_score": 0.0,
        "support_score": None,
        "composite_score": None,
    }


def search_crossref(
    query: str,
    year_range: tuple[int, int] | None = None,
    limit: int = 10,
    mailto: str | None = None,
) -> list[dict]:
    params: dict = {
        "query.bibliographic": query,
        "rows": min(limit, 50),
        "mailto": mailto or POLITE_EMAIL,
    }
    # Crossref filter syntax: comma-separated key:value pairs; a type value
    # cannot use '|' (400) — journal articles are the main target here,
    # conference proceedings are covered by OpenAlex / Semantic Scholar.
    filters = ["type:journal-article"]
    if year_range:
        # Crossref requires YYYY-MM-DD in from/until-pub-date filters
        filters.append(
            f"from-pub-date:{year_range[0]}-01-01,until-pub-date:{year_range[1]}-12-31")
    params["filter"] = ",".join(filters)

    data = rate_limited_request(CROSSREF_URL, params=params,
                                headers={"User-Agent": USER_AGENT}, min_interval=0.5)
    if not data or "message" not in data:
        return []
    items = (data.get("message") or {}).get("items") or []
    return [_to_unified(item) for item in items]


if __name__ == "__main__":
    import sys
    import json
    import argparse
    p = argparse.ArgumentParser(description="Crossref search")
    p.add_argument("query")
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()
    yr = (args.from_year, args.to_year) if (args.from_year or args.to_year) else None
    json.dump(search_crossref(args.query, yr, args.limit), sys.stdout, ensure_ascii=False, indent=2)
