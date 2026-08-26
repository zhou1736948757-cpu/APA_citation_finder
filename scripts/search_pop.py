"""APA_citation_finder :: search_pop.py
Optional Publish-or-Perish source — pop8query CLI (Harzing, free for
personal non-profit use). One binary gives us OpenAlex / Crossref /
Semantic Scholar / PubMed / Lens / Google Scholar channels with its own
result cache and adaptive rate limiting.

Why this source exists:
  * Google Scholar channel (--gscholar) is a far more stable GS route than
    the scholarly library (CAPTCHA still possible; CLI then terminates).
  * OpenAlex/Crossref/S2 channels are redundant fallbacks when the direct
    APIs are rate-limited.
  * PoP caches results on disk, so repeated queries cost no network.

Lazy-load contract: if pop8query is not found, warn and return [] — the
core flow (OpenAlex/S2/Crossref direct APIs) never depends on this.

Usage:
  python search_pop.py --query "unified theory of acceptance..." --output pop.json
  python search_pop.py --query "..." --channel gscholar --limit 10
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from utils.jsonl import write_json

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
POP_BIN = "pop8query"

# channel -> pop8query datasource flag
CHANNELS = {
    "openalex": "--openalex",
    "crossref": "--crossref",
    "semscholar": "--semscholar",
    "pubmed": "--pubmed",
    "gscholar": "--gscholar",
    "lens": "--lens",
}


def _find_pop() -> str | None:
    """Locate pop8query: skill tools/ dir first, then PATH."""
    local = TOOLS_DIR / POP_BIN
    if local.exists():
        return str(local)
    return shutil.which(POP_BIN)


def _to_unified(rec: dict) -> dict:
    """Map a pop8query JSONL record to the unified candidate schema."""
    authors = []
    for a in rec.get("authors") or []:
        name = (a.get("name") or "").strip() if isinstance(a, dict) else str(a).strip()
        if not name:
            continue
        # 'Given Family' -> 'Family, Given' (unified schema); keep as-is if comma form
        if "," not in name:
            parts = name.split()
            if len(parts) >= 2:
                name = f"{parts[-1]}, {' '.join(parts[:-1])}"
        authors.append(name)
    return {
        "title": rec.get("title") or "",
        "authors": authors,
        "year": rec.get("year"),
        "venue": rec.get("source") or rec.get("publisher") or "",
        "doi": (rec.get("doi") or "").strip() or None,
        "abstract": rec.get("abstract") or "",
        "volume": rec.get("volume"),
        "issue": rec.get("issue"),
        "pages": _pages(rec),
        "citations": rec.get("cites"),
        "source": "publish_or_perish",
        "source_apis": ["publish_or_perish"],
        "pop_uid": rec.get("uid"),
    }


def _pages(rec: dict) -> str:
    sp, ep = rec.get("startpage"), rec.get("endpage")
    if sp and ep:
        return f"{sp}-{ep}"
    return sp or ep or ""


def search_pop(query: str, year_range: tuple[int, int] | None = None,
               limit: int = 10, channel: str = "openalex",
               pop_path: str | None = None) -> list[dict]:
    """Search via pop8query; returns unified candidates ([] on any failure)."""
    pop = pop_path or _find_pop()
    if not pop:
        print("[APA_citation_finder] pop8query not found — Publish-or-Perish "
              "source skipped (install: see scripts/install_optional.py)",
              file=sys.stderr)
        return []
    flag = CHANNELS.get(channel)
    if not flag:
        print(f"[APA_citation_finder] unknown pop channel '{channel}'", file=sys.stderr)
        return []

    cmd = [pop, flag]
    # OpenAlex title.search accepts a single term; pair a title keyword with
    # the full query in keywords for precision without 400s.
    first_word = next((w for w in query.split() if len(w) > 2), query)
    cmd += ["--title", first_word, "--keywords", query]
    if year_range:
        cmd += ["--years", f"{year_range[0]}-{year_range[1]}"]
    cmd += ["--max", str(limit), "--format", "jsonl"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"[APA_citation_finder] pop8query failed: {e}", file=sys.stderr)
        return []
    if r.returncode not in (0, 4):  # 4 = no matches
        print(f"[APA_citation_finder] pop8query error ({r.returncode}): "
              f"{(r.stderr or '').strip()[:200]}", file=sys.stderr)
        return []
    if not r.stdout.strip():
        return []

    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line.lstrip("\ufeff"))
        except json.JSONDecodeError:
            continue
        u = _to_unified(rec)
        if u["title"]:
            out.append(u)
    return out


def _cli() -> int:
    p = argparse.ArgumentParser(description="Publish-or-Perish optional source")
    p.add_argument("--query", required=True)
    p.add_argument("--channel", default="openalex",
                   choices=sorted(CHANNELS), help="pop8query datasource")
    p.add_argument("--from-year", type=int, default=None)
    p.add_argument("--to-year", type=int, default=None)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--output", "-o", default="pop_papers.json")
    p.add_argument("--pop-path", default=None, help="explicit pop8query binary")
    args = p.parse_args()

    yr = None
    if args.from_year or args.to_year:
        yr = (args.from_year or 1900, args.to_year or 2100)
    papers = search_pop(args.query, yr, args.limit, args.channel, args.pop_path)
    write_json(args.output, papers)
    print(f"pop8query [{args.channel}]: {len(papers)} papers → {args.output}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
