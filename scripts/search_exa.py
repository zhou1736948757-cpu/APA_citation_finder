"""APA_citation_finder :: search_exa.py
Optional Exa source — semantic web discovery / hard-to-find content.
OFF by default. Requires EXA_API_KEY in skill .env (lazy-loaded; the core
pipeline never depends on this module).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from utils.ids import normalize_doi

SKILL_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = SKILL_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _get_client():
    try:
        from exa_py import Exa
    except ImportError:
        raise RuntimeError("exa-py not installed: pip install exa-py")
    _load_dotenv()
    key = os.getenv("EXA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("EXA_API_KEY missing in .env — Exa disabled")
    return Exa(key)


def _to_unified(item: dict) -> dict:
    meta = item.get("metadata") or {}
    doi = normalize_doi(meta.get("doi"))
    authors = []
    for a in (meta.get("authors") or [])[:20]:
        if isinstance(a, dict):
            name = " ".join(x for x in (a.get("first_name"), a.get("last_name")) if x)
        else:
            name = str(a)
        if name:
            parts = name.split()
            authors.append(f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) >= 2 else name)
    return {
        "title": meta.get("title") or item.get("title") or "",
        "authors": authors,
        "year": meta.get("year") or meta.get("publishedDate", "")[:4] or None,
        "journal": meta.get("journal") or meta.get("venue") or "",
        "venue": meta.get("journal") or meta.get("venue") or "",
        "venue_type": "journal" if meta.get("journal") else "other",
        "doi": doi,
        "url": item.get("url"),
        "abstract": meta.get("description") or item.get("highlight") or meta.get("summary") or "",
        "citation_count": 0,
        "volume": meta.get("volume"),
        "issue": None,
        "pages": None,
        "publisher": meta.get("publisher"),
        "issn_l": None,
        "issn": [],
        "open_access_pdf": None,
        "is_oa": False,
        "oa_status": None,
        "language": None,
        "keywords": [],
        "source_layer": "web",
        "source": "exa",
        "source_apis": ["exa"],
        "tier_score": 0.0,
        "recency_score": 0.0,
        "support_score": None,
        "composite_score": None,
    }


def search_exa(query: str, max_results: int = 10, category: str = "research paper") -> list[dict]:
    client = _get_client()
    resp = client.search_and_contents(
        query,
        num_results=max_results,
        category=category,
        text={"max_characters": 1500},
        summary=True,
    )
    out = []
    for item in resp.results or []:
        out.append(_to_unified(item))
    return out


if __name__ == "__main__":
    import argparse
    import json
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--max", type=int, default=10)
    args = p.parse_args()
    json.dump(search_exa(args.query, args.max), sys.stdout, ensure_ascii=False, indent=2)
