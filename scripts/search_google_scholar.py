"""APA_citation_finder :: search_google_scholar.py
Optional Google Scholar source — fallback only.
OFF by default (CAPTCHA / rate limits / fragile scraping / proxy dependence).
Requires: pip install scholarly. Optional proxy via env SCI_CITE_GS_PROXY.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any

from utils.ids import normalize_doi

try:
    from scholarly import scholarly
    SCHOLARLY_AVAILABLE = True
except ImportError:
    SCHOLARLY_AVAILABLE = False


def _to_unified(item: dict) -> dict:
    bib = item.get("bib") or {}
    title = bib.get("title") or ""
    raw_authors = bib.get("author") or []
    authors = []
    for name in raw_authors if isinstance(raw_authors, list) else []:
        name = str(name).strip()
        if not name:
            continue
        parts = name.split()
        authors.append(f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) >= 2 else name)
    try:
        year = int(bib.get("pub_year")) if bib.get("pub_year") else None
    except (TypeError, ValueError):
        year = None
    venue = bib.get("venue") or ""
    doi = normalize_doi(bib.get("doi"))
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": venue,
        "venue": venue,
        "venue_type": "journal" if venue else "other",
        "doi": doi,
        "url": item.get("pub_url"),
        "abstract": bib.get("abstract") or "",
        "citation_count": 0,
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
        "source_layer": "web",
        "source": "google_scholar",
        "source_apis": ["google_scholar"],
        "tier_score": 0.0,
        "recency_score": 0.0,
        "support_score": None,
        "composite_score": None,
    }


def search_google_scholar(
    query: str,
    limit: int = 10,
    year_start: int | None = None,
    sort_by: str = "relevance",
    use_proxy: bool = False,
) -> list[dict]:
    if not SCHOLARLY_AVAILABLE:
        raise RuntimeError("scholarly not installed: pip install scholarly")
    if use_proxy or os.getenv("SCI_CITE_GS_PROXY"):
        try:
            from scholarly import ProxyGenerator
            pg = ProxyGenerator()
            if pg.FreeProxies():
                scholarly.use_proxy(pg)
        except Exception:
            pass
    search_query = scholarly.search_pubs(query)
    out: list[dict] = []
    for i, item in enumerate(search_query):
        if i >= limit:
            break
        if year_start:
            bib = item.get("bib") or {}
            try:
                yr = int(bib.get("pub_year")) if bib.get("pub_year") else None
            except (TypeError, ValueError):
                yr = None
            if yr and yr < year_start:
                continue
        try:
            out.append(_to_unified(item))
        except Exception:
            continue
    return out


if __name__ == "__main__":
    import argparse
    import json
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--year-start", type=int)
    args = p.parse_args()
    json.dump(search_google_scholar(args.query, args.limit, args.year_start),
              sys.stdout, ensure_ascii=False, indent=2)
