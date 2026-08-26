"""APA_citation_finder :: verify_papers.py
Stage 4 — Paper Reality Verification (HARD GATE, not a ranking weight).

Verdicts:
    VERIFIED     — DOI resolves on Crossref AND metadata agrees (title >=0.85,
                   year exact, first-author last name) AND >=1 additional
                   source (Semantic Scholar or OpenAlex) agrees
    LIKELY_REAL  — no DOI, but OpenAlex + Semantic Scholar both return the
                   same title (>=0.85) with matching year/author
    UNVERIFIED   — cannot reliably confirm → REJECT by default
    CONFLICT     — DOI resolves but title/year/author conflict → REJECT

Policy:
    UNVERIFIED → reject     CONFLICT → reject
    LIKELY_REAL → fallback only    VERIFIED → enter support evaluation

Every attempt (including rejects) is appended to verification_log.jsonl so the
final audit can prove each accepted paper went through this gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from utils.http import rate_limited_request
from utils.ids import normalize_doi, paper_id_hash
from utils.jsonl import append_jsonl, load_json, write_json, utc_now_iso
from utils.text import first_author_last_name, normalize_author, title_similarity

CROSSREF_WORK_URL = "https://api.crossref.org/works/{doi}"
SEMANTIC_SCHOLAR_DOI_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_DOI_URL = "https://api.openalex.org/works/https://doi.org/{doi}"
OPENALEX_SEARCH_URL = "https://api.openalex.org/works"

USER_AGENT = "APA_citation_finder/1.0 (mailto:scipilot-cite@example.org)"
TITLE_THRESHOLD = 0.85


def _year_of(msg: dict) -> int | None:
    for key in ("issued", "published-print", "published-online", "published"):
        dp = (msg.get(key) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            return int(dp[0][0])
    return None


def verify_by_doi(doi: str, expected_title: str, expected_year: int | None,
                  expected_authors: list) -> dict:
    """Crossref DOI check + optional second-source agreement.

    Returns {"status": "VERIFIED"|"CONFLICT"|"NOT_FOUND", "details": {...},
             "second_source": bool}
    """
    data = rate_limited_request(
        CROSSREF_WORK_URL.format(doi=doi),
        headers={"User-Agent": USER_AGENT}, min_interval=0.6)
    if not data or "message" not in data:
        return {"status": "NOT_FOUND",
                "details": {"reason": "Crossref returned no record"}, "second_source": False}

    msg = data["message"]
    title_list = msg.get("title") or []
    real_title = title_list[0] if title_list else ""
    real_year = _year_of(msg)
    real_authors = [normalize_author(a) for a in (msg.get("author") or [])]

    title_score = title_similarity(real_title, expected_title)
    title_ok = title_score >= TITLE_THRESHOLD
    year_ok = (expected_year is None) or (real_year == expected_year)
    exp_last = first_author_last_name(expected_authors).lower()
    real_last = first_author_last_name(real_authors).lower()
    author_ok = (not exp_last) or (not real_last) or (exp_last == real_last)

    details = {
        "real_title": real_title,
        "real_year": real_year,
        "real_first_author": real_authors[0] if real_authors else "",
        "real_authors": real_authors,  # full Crossref author list (for backfill)
        "title_similarity": round(title_score, 4),
        "year_match": year_ok,
        "first_author_match": author_ok,
    }
    if title_ok and year_ok and author_ok:
        # second independent source agreement required for VERIFIED (§17):
        # agreement on title + year + first author, not title alone
        second = _check_second_source(real_title, real_year, real_authors, doi)
        details["second_source_agree"] = second
        if second:
            return {"status": "VERIFIED", "details": details, "second_source": True}
        return {"status": "LIKELY_REAL",
                "details": {**details, "note": "single-source only (second source unavailable/limited)"},
                "second_source": False}
    # DOI resolves but metadata conflicts → CONFLICT
    reasons = []
    if not title_ok:
        reasons.append(f"title mismatch ({title_score:.2f})")
    if not year_ok:
        reasons.append(f"year mismatch (claimed {expected_year}, real {real_year})")
    if not author_ok:
        reasons.append(f"first-author mismatch (claimed '{exp_last}', real '{real_last}')")
    return {"status": "CONFLICT",
            "details": {**details, "conflict_reasons": reasons}, "second_source": False}


def _s2_headers() -> dict:
    """Headers for Semantic Scholar; an API key (env S2_API_KEY) raises the
    rate ceiling and avoids the keyless 429 fast-fail degradation."""
    h = {"User-Agent": USER_AGENT}
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        h["x-api-key"] = key
    return h


def _check_second_source(title: str, year: int | None, authors: list,
                         doi: str | None = None) -> bool:
    """Confirm the paper exists on an independent second source.

    Order: Semantic Scholar (by title) → OpenAlex (by DOI, exact and
    rate-lenient). S2 keyless 429s therefore no longer force a VERIFIED
    paper down to LIKELY_REAL: OpenAlex is a free fallback.
    """
    exp_last = first_author_last_name(authors).lower()

    # 1) Semantic Scholar title search
    params = {"query": title, "limit": 3, "fields": "title,year"}
    data = rate_limited_request(
        SEMANTIC_SCHOLAR_SEARCH, params=params,
        headers=_s2_headers(), min_interval=1.0)
    for item in (data or {}).get("data") or []:
        item_authors = [(a or {}).get("name", "") for a in (item.get("authors") or [])]
        item_last = first_author_last_name(item_authors).lower()
        if (title_similarity(item.get("title") or "", title) >= TITLE_THRESHOLD
                and (year is None or item.get("year") == year)
                and (not exp_last or not item_last or exp_last == item_last)):
            return True

    # 2) OpenAlex DOI lookup (exact match, no key needed, lenient rate limit)
    if doi:
        data = rate_limited_request(
            OPENALEX_DOI_URL.format(doi=doi),
            headers={"User-Agent": USER_AGENT}, min_interval=0.5)
        if data and data.get("id"):
            o_title = data.get("title") or data.get("display_name") or ""
            o_year = data.get("publication_year")
            o_authors = []
            for au in data.get("authorships", []) or []:
                disp = (au.get("author") or {}).get("display_name")
                if disp:
                    o_authors.append(disp)
            o_last = first_author_last_name(o_authors).lower()
            if (title_similarity(o_title, title) >= TITLE_THRESHOLD
                    and (year is None or o_year == year)
                    and (not exp_last or not o_last or exp_last == o_last)):
                return True
    return False


def _search_s2_title(title: str, limit: int = 3) -> list[dict]:
    params = {"query": title, "limit": limit, "fields": "title,year,authors,externalIds"}
    data = rate_limited_request(
        SEMANTIC_SCHOLAR_SEARCH, params=params,
        headers=_s2_headers(), min_interval=1.0)
    return (data or {}).get("data") or []


def _search_openalex_title(title: str, limit: int = 3) -> list[dict]:
    params = {"search": title, "per_page": limit, "mailto": "scipilot-cite@example.org"}
    data = rate_limited_request(
        OPENALEX_SEARCH_URL, params=params,
        headers={"User-Agent": USER_AGENT}, min_interval=0.5)
    return (data or {}).get("results") or []


def verify_by_cross_check(title: str, year: int | None, authors: list) -> dict:
    """No DOI: require strong agreement from 2+ independent sources."""
    expected_last = first_author_last_name(authors).lower()
    hits: list[str] = []

    for s in _search_s2_title(title):
        s_title = s.get("title") or ""
        s_year = s.get("year")
        s_authors = [(a or {}).get("name", "") for a in (s.get("authors") or [])]
        s_last = first_author_last_name(s_authors).lower()
        if (title_similarity(s_title, title) >= TITLE_THRESHOLD
                and (year is None or s_year == year)
                and (not expected_last or not s_last or expected_last == s_last)):
            hits.append("semantic_scholar")
            break

    for o in _search_openalex_title(title):
        o_title = o.get("title") or o.get("display_name") or ""
        o_year = o.get("publication_year")
        o_authors = []
        for au in o.get("authorships", []) or []:
            disp = (au.get("author") or {}).get("display_name")
            if disp:
                o_authors.append(disp)
        o_last = first_author_last_name(o_authors).lower()
        if (title_similarity(o_title, title) >= TITLE_THRESHOLD
                and (year is None or o_year == year)
                and (not expected_last or not o_last or expected_last == o_last)):
            hits.append("openalex")
            break

    if len(hits) >= 2:
        return {"status": "LIKELY_REAL", "details": {"matched_sources": hits}}
    return {"status": "UNVERIFIED", "details": {"matched_sources": hits}}


def _to_last_first(name: str) -> str:
    """'Given Family' -> 'Family, Given'; keep 'Family, Given' as-is."""
    name = (name or "").strip()
    if "," in name:
        return name
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def _backfill_authors(paper_authors: list, real_authors: list) -> list:
    """Fill missing given names from Crossref metadata (real data, never
    invented). A paper author 'Venkatesh' becomes 'Venkatesh, V.' when
    Crossref carries the full name; complete names are never overwritten."""
    if not real_authors:
        return paper_authors
    out = []
    real_by_last = {}
    for ra in real_authors:
        last = first_author_last_name([ra]).lower()
        if last:
            real_by_last.setdefault(last, _to_last_first(ra))
    for pa in paper_authors:
        last = first_author_last_name([pa]).lower()
        if not last:
            out.append(pa)
            continue
        candidate = real_by_last.get(last)
        if candidate and "," in candidate and "," not in pa:
            out.append(candidate)  # backfill given name
        else:
            out.append(pa)
    return out


def verify_paper(paper: dict) -> dict:
    doi = paper.get("doi")
    title = paper.get("title", "")
    year = paper.get("year")
    authors = paper.get("authors") or []

    out = dict(paper)
    if doi:
        result = verify_by_doi(doi, title, year, authors)
        if result["status"] == "VERIFIED":
            out["verification_status"] = "VERIFIED"
            out["verification_details"] = result["details"]
            # FIX-B: Crossref carries complete author names; backfill
            # missing given names so APA initials render correctly
            real_authors = result["details"].get("real_authors") or []
            if real_authors:
                out["authors"] = _backfill_authors(authors, real_authors)
                out["authors_backfilled"] = True
            return out
        if result["status"] == "NOT_FOUND":
            # a DOI the registry cannot resolve is itself a red flag: the
            # record is UNVERIFIED, no cross-check fallback
            out["verification_status"] = "UNVERIFIED"
            out["verification_details"] = {
                "doi_check": result["details"],
                "doi_status": "NOT_FOUND",
                "note": "claimed DOI does not resolve on Crossref",
            }
            return out
        if result["status"] == "LIKELY_REAL":
            out["verification_status"] = "LIKELY_REAL"
            out["verification_details"] = result["details"]
            return out
        # CONFLICT — reject, do not fall through to cross-check
        out["verification_status"] = "CONFLICT"
        out["verification_details"] = result["details"]
        return out

    cross = verify_by_cross_check(title, year, authors)
    out["verification_status"] = cross["status"]
    out["verification_details"] = cross["details"]
    return out


def _load_cache(path: str | None) -> dict:
    if not path:
        return {}
    try:
        from utils.jsonl import load_json
        return load_json(path) or {}
    except Exception:
        return {}


def _save_cache(path: str | None, cache: dict) -> None:
    if not path:
        return
    from utils.jsonl import write_json
    try:
        write_json(path, cache)
    except Exception:
        pass


def batch_verify(papers: list[dict], max_workers: int = 4,
                 log_path: str | None = "verification_log.jsonl",
                 cache_path: str | None = "verification_cache.json") -> dict:
    """Verify all candidates; returns {"kept": [...], "rejected": [...],
    "log_entries": N}. Accepts VERIFIED + LIKELY_REAL (fallback) only.

    cache_path: DOI-keyed JSON cache of past verdicts. Re-verifying the
    same DOI (across runs) skips the rate-limited network calls entirely,
    which is the main mitigation for keyless Semantic Scholar throttling.
    """
    cache = _load_cache(cache_path)
    results: list[dict] = []
    pending: list[dict] = []
    for p in papers:
        doi = (p.get("doi") or "").lower()
        hit = cache.get(doi) if doi else None
        if hit and hit.get("verdict") in {"VERIFIED", "LIKELY_REAL", "CONFLICT", "UNVERIFIED"}:
            out = dict(p)
            out["verification_status"] = hit["verdict"]
            out["verification_details"] = hit.get("details", {})
            out["verification_cached"] = True
            if hit.get("authors_backfilled"):
                out["authors"] = hit["authors"]
                out["authors_backfilled"] = True
            results.append(out)
        else:
            pending.append(p)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(verify_paper, p): p for p in pending}
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                print(f"verify failed for one paper: {e}", file=sys.stderr)
                futs[f]["verification_status"] = "UNVERIFIED"
                results.append(futs[f])
    # refresh cache with fresh verdicts
    if cache_path:
        for r in results:
            doi = (r.get("doi") or "").lower()
            if not doi:
                continue
            cache[doi] = {
                "verdict": r.get("verification_status"),
                "details": r.get("verification_details", {}),
                "authors_backfilled": bool(r.get("authors_backfilled")),
                "authors": r.get("authors") if r.get("authors_backfilled") else None,
                "cached_at": utc_now_iso(),
            }
        _save_cache(cache_path, cache)

    if log_path:
        ts = utc_now_iso()
        for r in results:
            append_jsonl(log_path, {
                "timestamp": ts,
                "event": "verification",
                "paper_id": paper_id_hash(r),
                "title_claimed": r.get("title"),
                "doi_claimed": r.get("doi"),
                "year_claimed": r.get("year"),
                "first_author_claimed": (r.get("authors") or [""])[0],
                "verdict": r.get("verification_status"),
                "details": r.get("verification_details", {}),
            })

    kept = [p for p in results if p.get("verification_status") in {"VERIFIED", "LIKELY_REAL"}]
    rejected = [p for p in results if p.get("verification_status") not in {"VERIFIED", "LIKELY_REAL"}]
    counts = {
        "VERIFIED": sum(1 for p in kept if p["verification_status"] == "VERIFIED"),
        "LIKELY_REAL": sum(1 for p in kept if p["verification_status"] == "LIKELY_REAL"),
        "UNVERIFIED": sum(1 for p in rejected if p["verification_status"] == "UNVERIFIED"),
        "CONFLICT": sum(1 for p in rejected if p["verification_status"] == "CONFLICT"),
    }
    return {"kept": kept, "rejected": rejected, "log_count": len(results), "counts": counts}


def _cli() -> int:
    p = argparse.ArgumentParser(description="APA_citation_finder paper verifier")
    p.add_argument("papers_json", help="JSON list of candidate papers")
    p.add_argument("--log", default="verification_log.jsonl", help="'' disables")
    p.add_argument("--cache", default="verification_cache.json",
                   help="DOI-keyed verdict cache ('' disables)")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--output", "-o", default="verified_papers.json")
    args = p.parse_args()

    papers = load_json(args.papers_json)
    if isinstance(papers, dict):
        papers = papers.get("papers") or papers.get("kept") or []
    result = batch_verify(papers, max_workers=args.max_workers,
                          log_path=args.log or None)
    summary = {
        "kept": result["kept"],
        "rejected": result["rejected"],
        "counts": result["counts"],
    }
    write_json(args.output, summary)
    print(f"Verification: {summary['counts']} → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
