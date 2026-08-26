"""APA_citation_finder :: utils/ids.py
Stable identifiers: paper_id, claim_id, bibtex keys, DOI normalization.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .text import first_author_last_name, _STOPWORDS


def normalize_doi(doi: str | None) -> str | None:
    """Lower-case, strip URL prefix / trailing punctuation. None → None."""
    if not doi:
        return None
    d = str(doi).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.rstrip(".,;")


def paper_id_hash(paper: dict) -> str:
    """Stable 16-char hex id from DOI (preferred) or (norm_title|year|first_author_last).

    Binds a paper across search → verify → evidence → support → audit stages.
    """
    doi = normalize_doi(paper.get("doi"))
    if doi:
        seed = f"doi:{doi}"
    else:
        raw_title = (paper.get("title") or "").lower()
        norm_title = re.sub(r"[^\w\s]", " ", raw_title)
        norm_title = re.sub(r"\s+", " ", norm_title).strip()
        year = str(paper.get("year") or "")
        first_last = first_author_last_name(paper.get("authors") or []).lower()
        seed = f"title:{norm_title}|year:{year}|author:{first_last}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def make_bibtex_key(paper: dict) -> str:
    """FirstAuthorLastName_Year_FirstKeyword (unique enough; deduped downstream)."""
    authors = paper.get("authors", []) or []
    first_last = "unknown"
    if authors:
        first_last = (first_author_last_name([authors[0]]) or "unknown")
        first_last = re.sub(r"[^A-Za-z]", "", first_last) or "unknown"
    year = paper.get("year") or "xxxx"
    title = paper.get("title", "") or ""
    keyword = "paper"
    for w in re.findall(r"\b[A-Za-z]+\b", title):
        if len(w) >= 4 and w.lower() not in _STOPWORDS:
            keyword = w.lower()
            break
    key = f"{first_last}_{year}_{keyword}"
    # BibTeX keys must be ASCII-ish and free of braces/commas
    key = re.sub(r"[^A-Za-z0-9_:]", "", key)
    return key or "paper"


def assign_citation_numbers(insertion_plan: list[dict]) -> list[dict]:
    """Assign [1],[2],... by first-appearance document order.

    Each item needs 'paper_idx' and a comparable 'position'.
    Items for the same paper keep the same number.
    """
    sorted_plan = sorted(insertion_plan, key=lambda x: (x.get("position", 0), x.get("paper_idx", 0)))
    paper_to_num: dict[int, int] = {}
    out: list[dict] = []
    next_num = 1
    for item in sorted_plan:
        pid = item["paper_idx"]
        if pid not in paper_to_num:
            paper_to_num[pid] = next_num
            next_num += 1
        new_item = dict(item)
        new_item["citation_number"] = paper_to_num[pid]
        out.append(new_item)
    return out


def claim_id_from_index(idx: int) -> str:
    return f"C{idx:03d}"
