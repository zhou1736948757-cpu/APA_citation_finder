"""APA_citation_finder :: deduplicate.py
Stage 3 — Multi-source deduplication + field merge.

Rules (from spec §16):
  * DOI exact / normalized DOI → merge
  * DOI absent AND title_similarity >= 0.90 AND year close AND first-author
    last name match → likely duplicate → merge
  * merge keeps the longest/fullest field values; citation_count = max;
    source_apis[] records every source that returned the paper
"""
from __future__ import annotations

from typing import Any

from utils.ids import normalize_doi, paper_id_hash
from utils.text import title_similarity

SOURCE_PRIORITY = {
    "crossref": 0,          # most authoritative metadata
    "openalex": 1,
    "semantic_scholar": 2,
    "local_file": 4,
    "exa": 5,
    "google_scholar": 6,
}

_PRIO_FIELDS = ("doi", "title", "authors", "venue", "journal", "abstract", "issn_l", "issn")
_MERGE_FIELDS = (
    "title", "authors", "venue", "journal", "abstract", "citation_count",
    "issn_l", "issn", "volume", "issue", "pages", "publisher",
    "url", "open_access_pdf", "is_oa", "oa_status", "language", "keywords",
    "year", "venue_type",
)


def _source_priority(paper: dict) -> int:
    return SOURCE_PRIORITY.get(paper.get("source", ""), 9)


def _field_quality(val: Any, field: str) -> int:
    if val is None:
        return -1
    if field == "authors" and isinstance(val, list):
        # prefer the source with the most complete names ("Last, First")
        complete = sum(1 for a in val if isinstance(a, str) and "," in a)
        return complete * 1000 + len(val) * 10 + sum(len(str(a)) for a in val)
    if isinstance(val, list):
        return len(val)
    if isinstance(val, str):
        return len(val)
    if isinstance(val, bool):
        return 1 if val else -1
    if isinstance(val, (int, float)):
        return 0 if val == 0 else 1
    return 0


def _merge_group(group: list[dict]) -> dict:
    group = sorted(group, key=lambda r: _source_priority(r))
    best = dict(group[0])
    for other in group[1:]:
        for field in _MERGE_FIELDS:
            bv, ov = best.get(field), other.get(field)
            if field == "citation_count":
                best[field] = max(best.get(field, 0) or 0, other.get(field, 0) or 0)
                continue
            bq, oq = _field_quality(bv, field), _field_quality(ov, field)
            if oq < 0:
                continue
            if bq < 0:
                best[field] = ov
                continue
            if field in _PRIO_FIELDS and field != "authors":
                if _source_priority(other) < _source_priority(best):
                    best[field] = ov
            else:
                if oq > bq:
                    best[field] = ov
    # merge source_apis / source
    apis: list[str] = []
    for r in group:
        for a in r.get("source_apis") or []:
            if a not in apis:
                apis.append(a)
    if not apis:
        apis = list(dict.fromkeys(r.get("source", "") for r in group if r.get("source")))
    best["source_apis"] = apis
    best["source"] = "+".join(apis) if apis else best.get("source", "")
    best["paper_id"] = paper_id_hash(best)
    return best


def _years_close(y1: Any, y2: Any) -> bool:
    if not y1 or not y2:
        return True  # unknown year does not block merge
    try:
        return abs(int(y1) - int(y2)) <= 1
    except (TypeError, ValueError):
        return True


def _first_author_last(paper: dict) -> str:
    authors = paper.get("authors") or []
    if not authors:
        return ""
    name = authors[0]
    if "," in name:
        return name.split(",", 1)[0].strip().lower()
    parts = str(name).split()
    return parts[-1].lower().strip(",.") if parts else ""


def deduplicate(results: list[dict]) -> list[dict]:
    """Dedupe across all sources. Returns merged list (order preserved by first
    occurrence of each paper)."""
    by_doi: dict[str, list[dict]] = {}
    no_doi: list[dict] = []
    for r in results:
        doi = normalize_doi(r.get("doi"))
        if doi:
            by_doi.setdefault(doi, []).append(r)
        else:
            no_doi.append(r)

    merged: list[dict] = [_nice_group(g) for g in by_doi.values()]

    # fuzzy match for no-DOI papers against existing merged (with DOI) and each other
    for p in no_doi:
        match_idx = None
        for i, m in enumerate(merged):
            if not _years_close(p.get("year"), m.get("year")):
                continue
            if _first_author_last(p) and _first_author_last(m) and \
                    _first_author_last(p) != _first_author_last(m):
                continue
            if title_similarity(p.get("title", ""), m.get("title", "")) >= 0.90:
                match_idx = i
                break
        if match_idx is not None:
            merged[match_idx] = _nice_group([merged[match_idx], p])
        else:
            merged.append(p)

    for p in merged:
        p["paper_id"] = paper_id_hash(p)
    return merged


def _nice_group(group: list[dict]) -> dict:
    return _merge_group(group)


def deduplicate_pairs(a: list[dict], b: list[dict]) -> list[dict]:
    """Merge two already-deduped lists (e.g. search results + local)."""
    return deduplicate(a + b)
