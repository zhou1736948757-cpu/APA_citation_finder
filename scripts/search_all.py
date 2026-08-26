"""APA_citation_finder :: search_all.py
Stage 2 — Retrieval orchestrator.

Runs per claim (or single query):
  core:      OpenAlex + Semantic Scholar (semantic discovery), Crossref (metadata)
  optional:  Exa, Google Scholar, Publish-or-Perish, Local files — only when enabled

Writes search_log.jsonl (one record per candidate result) so every candidate
is traceable to a real API response. Uses search budget:
  initial candidates per claim = target × 3 (default)
  max_search_rounds / max_candidates_per_claim configurable

Usage:
  python search_all.py --query "..." --output claim_C001.json
  python search_all.py --claim-json claims.json --output-dir runs/
  python search_all.py --query "..." --sources core,exa
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from search_openalex import search_openalex
from search_semantic_scholar import search_semantic_scholar
from search_crossref import search_crossref
from deduplicate import deduplicate
from utils.journal import filter_blacklisted, compute_tier_score, recency_score
from utils.jsonl import append_jsonl, write_json, load_json, utc_now_iso
from utils.ids import paper_id_hash

POLITE_EMAIL = "scipilot-cite@example.org"

SOURCE_IMPORTERS = {
    "exa": "search_exa",
    "google_scholar": "search_google_scholar",
    "pop": "search_pop",
    "local": "search_local",
}


def _search_one(
    query: str,
    year_range: tuple[int, int] | None,
    limit: int,
    email: str | None,
    sources: list[str],
) -> list[dict]:
    """Run enabled sources for one query; returns raw (undeduped) results."""
    results: list[dict] = []
    errors: list[str] = []
    core = [s for s in sources if s in ("openalex", "semantic_scholar", "crossref")]
    enhanced = [s for s in sources if s not in ("openalex", "semantic_scholar", "crossref")]

    def _run_core():
        out = []
        with ThreadPoolExecutor(max_workers=len(core) or 1) as ex:
            futs = {}
            if "openalex" in core:
                futs[ex.submit(search_openalex, query, year_range, limit, email)] = "openalex"
            if "semantic_scholar" in core:
                futs[ex.submit(search_semantic_scholar, query, year_range, limit)] = "semantic_scholar"
            if "crossref" in core:
                futs[ex.submit(search_crossref, query, year_range, limit, email)] = "crossref"
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    r = fut.result() or []
                    out.extend(r)
                except Exception as e:
                    errors.append(f"{name}: {e}")
        return out

    core_results = _run_core_impl(core, query, year_range, limit, email, errors)
    results.extend(core_results)

    for name in enhanced:
        mod_name = SOURCE_IMPORTERS.get(name)
        if not mod_name:
            errors.append(f"unknown source {name}")
            continue
        try:
            mod = __import__(mod_name)
            if name == "exa":
                fn = getattr(mod, "search_exa")
                r = fn(query=query, max_results=limit)
            elif name == "google_scholar":
                fn = getattr(mod, "search_google_scholar")
                r = fn(query=query, limit=limit, year_start=year_range[0] if year_range else None)
            elif name == "pop":
                fn = getattr(mod, "search_pop")
                r = fn(query=query, year_range=year_range, limit=limit)
            elif name == "local":
                fn = getattr(mod, "search_local")
                r = fn(query=query, limit=limit)
            else:
                r = []
            results.extend(r or [])
        except Exception as e:
            errors.append(f"{name}: {e}")

    if errors:
        for e in errors:
            print(f"  Warning: {e}", file=sys.stderr)
    return results


def _run_core_impl(core, query, year_range, limit, email, errors):
    out = []
    if not core:
        return out
    with ThreadPoolExecutor(max_workers=len(core)) as ex:
        futs = {}
        if "openalex" in core:
            futs[ex.submit(search_openalex, query, year_range, limit, email)] = "openalex"
        if "semantic_scholar" in core:
            futs[ex.submit(search_semantic_scholar, query, year_range, limit)] = "semantic_scholar"
        if "crossref" in core:
            futs[ex.submit(search_crossref, query, year_range, limit, email)] = "crossref"
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                out.extend(fut.result() or [])
            except Exception as e:
                errors.append(f"{name}: {e}")
    return out


def enrich(paper: dict, email: str | None) -> dict:
    if not paper.get("tier_score"):
        paper["tier_score"] = round(compute_tier_score(paper, mailto=email), 4)
    if not paper.get("recency_score"):
        paper["recency_score"] = round(recency_score(paper.get("year")), 4)
    return paper


def search_all(
    query: str,
    year_range: tuple[int, int] | None = None,
    limit: int = 10,
    email: str | None = None,
    sources: list[str] | None = None,
    log_path: str | None = "search_log.jsonl",
    extra_results: list[dict] | None = None,
) -> list[dict]:
    """Search + dedupe + blacklist + enrich. Returns final paper list."""
    if sources is None:
        sources = ["openalex", "semantic_scholar", "crossref"]
    raw = _search_one(query, year_range, limit, email, sources)
    if extra_results:
        raw.extend(extra_results)
    merged = deduplicate(raw)
    merged = filter_blacklisted(merged)
    merged = [enrich(p, email) for p in merged]

    if log_path:
        ts = utc_now_iso()
        for p in merged:
            append_jsonl(log_path, {
                "timestamp": ts,
                "event": "search_result",
                "paper_id": paper_id_hash(p),
                "query": query,
                "title": p.get("title"),
                "doi": p.get("doi"),
                "year": p.get("year"),
                "venue": p.get("venue"),
                "first_author": (p.get("authors") or [""])[0],
                "citation_count": p.get("citation_count"),
                "source_apis": p.get("source_apis"),
            })
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="APA_citation_finder unified search")
    parser.add_argument("--query", help="single query")
    parser.add_argument("--claim-json", help="claims.json path (search each REQUIRED/RECOMMENDED claim)")
    parser.add_argument("--output-dir", default="runs", help="output dir for claim_<id>.json")
    parser.add_argument("--from-year", type=int)
    parser.add_argument("--to-year", type=int)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--email", default=None)
    parser.add_argument("--sources", default="core",
                        help="comma list: openalex,semantic_scholar,crossref,exa,google_scholar,pop,local | core")
    parser.add_argument("--log", default="search_log.jsonl", help="'' disables")
    args = parser.parse_args()

    if args.sources == "core":
        sources = ["openalex", "semantic_scholar", "crossref"]
    else:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    year_range = (args.from_year, args.to_year) if (args.from_year or args.to_year) else None
    log_path = args.log or None

    if args.claim_json:
        claims = load_json(args.claim_json)
        if isinstance(claims, dict):
            claims = claims.get("claims", [])
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        n_claims = 0
        for c in claims:
            if c.get("citation_need") in ("NOT_NEEDED",):
                continue
            queries = c.get("queries") or []
            if not queries:
                queries = [{"type": "precise",
                            "query": c.get("normalized_claim") or c.get("original_text") or ""}]
            # multi-query strategy: run every query type, cap total budget
            # per claim so one claim cannot starve the pipeline
            budget = max(1, args.limit // len(queries))
            all_papers: list[dict] = []
            for q in queries[:4]:  # precise/broad/synonym/domain (max 4)
                if not q.get("query"):
                    continue
                papers = search_all(q["query"], year_range, budget, args.email,
                                    sources, log_path)
                all_papers.extend(papers)
            target = out_dir / f"claim_{c['claim_id']}.json"
            write_json(str(target), all_papers)
            n_claims += 1
        print(f"Searched {n_claims} claims → {out_dir}", file=sys.stderr)
        return 0

    if not args.query:
        parser.error("--query or --claim-json required")
    papers = search_all(args.query, year_range, args.limit, args.email, sources, log_path)
    if args.output_dir != "runs":
        write_json(args.output_dir, papers)
    else:
        json.dump(papers, sys.stdout, ensure_ascii=False, indent=2)
    print(f"Final: {len(papers)} unique papers", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
