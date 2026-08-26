"""APA_citation_finder :: fetch_evidence.py
Stage 5 — Evidence retrieval.

Only papers that pass reality verification enter this stage. For each paper
we capture the best available evidence FOR THE CLAIM, preferring:

    FULL_TEXT passage  >  ABSTRACT  >  SUMMARY  >  METADATA_ONLY

Rules:
  * evidence_text must come from actually-retrieved content (abstract fields,
    API responses). The model must never synthesize an evidence quote.
  * evidence_level records what we actually got.
  * METADATA_ONLY evidence can never justify a strong support score (the cap
    is enforced in score_support.py).

Writes evidence_log.jsonl: one record per paper.
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from utils.http import rate_limited_request
from utils.ids import normalize_doi, paper_id_hash
from utils.jsonl import append_jsonl, load_json, write_json, utc_now_iso

USER_AGENT = "APA_citation_finder/1.0 (mailto:scipilot-cite@example.org)"
OPENALEX_DOI_URL = "https://api.openalex.org/works/https://doi.org/{doi}"
S2_DOI_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
ARXIV_API_URL = "http://export.arxiv.org/api/query"

MAX_EVIDENCE_CHARS = 2000


def _abstract_from_openalex(doi: str) -> str | None:
    data = rate_limited_request(OPENALEX_DOI_URL.format(doi=doi),
                                headers={"User-Agent": USER_AGENT}, min_interval=0.5)
    if not data:
        return None
    inv = data.get("abstract_inverted_index")
    if not inv:
        return None
    pos: list[tuple[int, str]] = []
    for word, plist in inv.items():
        for p in plist or []:
            pos.append((p, word))
    pos.sort()
    return " ".join(w for _, w in pos) or None


def _abstract_from_s2(doi: str) -> str | None:
    data = rate_limited_request(
        S2_DOI_URL.format(doi=doi),
        params={"fields": "title,abstract,openAccessPdf,externalIds"},
        headers={"User-Agent": USER_AGENT}, min_interval=1.0)
    if not data:
        return None
    return (data.get("abstract") or "").strip() or None


def _fulltext_arxiv(paper: dict) -> str | None:
    """Best-effort arXiv summary via arXiv API (only when an arXiv id exists)."""
    arxiv_id = None
    url = paper.get("url") or ""
    if "arxiv.org/abs/" in url:
        arxiv_id = url.rsplit("/", 1)[-1]
    elif (paper.get("venue") or "").lower().startswith("arxiv"):
        arxiv_id = paper.get("doi")
    if not arxiv_id:
        return None
    try:
        resp = rate_limited_request(ARXIV_API_URL,
                                    params={"id_list": arxiv_id},
                                    min_interval=3.0, timeout=30)
        if resp and "<summary>" in resp:
            m = re.search(r"<summary>(.*?)</summary>", resp, re.S)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()[:MAX_EVIDENCE_CHARS]
    except Exception:
        pass
    return None


def fetch_evidence_for_paper(paper: dict) -> dict:
    """Best-effort evidence: stored abstract > OpenAlex > S2 > arXiv summary."""
    out = dict(paper)
    abstract = (paper.get("abstract") or "").strip()
    if abstract:
        out["evidence_level"] = "ABSTRACT"
        out["evidence_source"] = "search_result"
        out["evidence_text"] = abstract[:MAX_EVIDENCE_CHARS]
        return out

    doi = normalize_doi(paper.get("doi"))
    if doi:
        for fn, src in ((_abstract_from_openalex, "openalex"),
                        (_abstract_from_s2, "semantic_scholar")):
            try:
                txt = fn(doi)
            except Exception:
                txt = None
            if txt:
                out["evidence_level"] = "ABSTRACT"
                out["evidence_source"] = src
                out["evidence_text"] = txt[:MAX_EVIDENCE_CHARS]
                return out
    try:
        txt = _fulltext_arxiv(paper)
    except Exception:
        txt = None
    if txt:
        out["evidence_level"] = "SUMMARY"
        out["evidence_source"] = "arxiv_api"
        out["evidence_text"] = txt[:MAX_EVIDENCE_CHARS]
        return out

    out["evidence_level"] = "METADATA_ONLY"
    out["evidence_source"] = "title_metadata"
    out["evidence_text"] = ""
    return out


def fetch_evidence(papers: list[dict], max_workers: int = 4,
                   log_path: str | None = "evidence_log.jsonl") -> list[dict]:
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fetch_evidence_for_paper, p): p for p in papers}
        out: list[dict] = []
        for f in as_completed(futs):
            try:
                out.append(f.result())
            except Exception:
                p = dict(futs[f])
                p["evidence_level"] = "METADATA_ONLY"
                p["evidence_source"] = "title_metadata"
                p["evidence_text"] = ""
                out.append(p)
    if log_path:
        ts = utc_now_iso()
        for p in out:
            append_jsonl(log_path, {
                "timestamp": ts,
                "event": "evidence",
                "paper_id": paper_id_hash(p),
                "title": p.get("title"),
                "doi": p.get("doi"),
                "evidence_level": p.get("evidence_level"),
                "evidence_source": p.get("evidence_source"),
                "evidence_chars": len(p.get("evidence_text") or ""),
            })
    return out


def _cli() -> int:
    p = argparse.ArgumentParser(description="Fetch evidence for verified papers")
    p.add_argument("papers_json", help="verified papers JSON (list or {kept:[...]})")
    p.add_argument("--log", default="evidence_log.jsonl", help="'' disables")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--output", "-o", default="evidenced_papers.json")
    args = p.parse_args()

    data = load_json(args.papers_json)
    if isinstance(data, dict) and "kept" in data:
        papers = data["kept"]
    elif isinstance(data, list):
        papers = data
    else:
        papers = []
    evidenced = fetch_evidence(papers, args.max_workers)
    if args.log:
        ts = utc_now_iso()
        for p in evidenced:
            append_jsonl(args.log, {
                "timestamp": ts,
                "event": "evidence",
                "paper_id": paper_id_hash(p),
                "title": p.get("title"),
                "doi": p.get("doi"),
                "evidence_level": p.get("evidence_level"),
                "evidence_source": p.get("evidence_source"),
                "evidence_text": (p.get("evidence_text") or "")[:500],
            })
    write_json(args.output, evidenced)
    levels: dict[str, int] = {}
    for p in evidenced:
        lvl = p.get("evidence_level", "?")
        levels[lvl] = levels.get(lvl, 0) + 1
    print(f"Evidence levels: {levels} → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
