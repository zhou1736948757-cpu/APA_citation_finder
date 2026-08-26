"""APA_citation_finder :: format_bibtex.py
Stage 8b — BibTeX output (references.bib).

Merges scipilot's entry builder (via format_citation.format_bibtex_entry) with
citation-finder's batch key-dedupe logic. Never duplicates an already-present
DOI (update_references.py checks existing .bib DOIs before appending).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from format_citation import format_bibtex_entry
from utils.ids import normalize_doi
from utils.jsonl import load_json

_MAIN_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_MAIN_SCRIPT_DIR))


def batch_to_bibtex(papers: list[dict], existing_dois: set[str] | None = None) -> str:
    """Format papers into a .bib string; skips DOIs already present."""
    existing_dois = existing_dois or set()
    entries: list[str] = []
    seen_keys: set[str] = set()
    for p in papers:
        doi = normalize_doi(p.get("doi"))
        if doi and doi in existing_dois:
            continue  # never duplicate the same DOI
        key = _dedupe_key(p, seen_keys)
        entries.append(format_bibtex_entry(p, key))
    return "\n\n".join(entries) + ("\n" if entries else "")


def _dedupe_key(paper: dict, seen: set[str]) -> str:
    from utils.ids import make_bibtex_key
    base = make_bibtex_key(paper)
    key = base
    i = 2
    while key in seen:
        key = f"{base}_{i}"
        i += 1
    seen.add(key)
    return key


def extract_dois_from_bib(bib_text: str) -> set[str]:
    """Parse existing .bib for DOI values (for no-duplicate guarantees)."""
    dois = set()
    for m in re.finditer(r"doi\s*=\s*\{([^}]+)\}", bib_text, re.I):
        d = normalize_doi(m.group(1))
        if d:
            dois.add(d)
    return dois


def _cli() -> int:
    p = argparse.ArgumentParser(description="Format papers as BibTeX")
    p.add_argument("--input", required=True, help="papers JSON (list or final_papers envelope)")
    p.add_argument("--output", default=None, help=".bib path (default stdout)")
    p.add_argument("--existing-bib", default=None, help="existing .bib to avoid DOI duplicates")
    args = p.parse_args()

    data = load_json(args.input)
    if isinstance(data, dict):
        papers = data.get("papers") or data.get("kept") or []
    else:
        papers = data
    existing_dois: set[str] = set()
    if args.existing_bib:
        existing_dois = extract_dois_from_bib(
            Path(args.existing_bib).read_text(encoding="utf-8"))
    bib = batch_to_bibtex(papers, existing_dois)
    if args.output:
        Path(args.output).write_text(bib, encoding="utf-8")
        print(f"Wrote {bib.count('@')} entries → {args.output}", file=sys.stderr)
    else:
        print(bib)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
