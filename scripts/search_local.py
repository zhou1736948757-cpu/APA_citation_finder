"""APA_citation_finder :: search_local.py
Optional Local-file source — user-provided PDF/DOCX/TXT/MD papers are
preferred candidates ("优先使用我提供的论文" flow).

Usage:
  python search_local.py --paths paper.pdf,note.md --output local_papers.json
  python search_local.py --dir ~/papers --output local_papers.json

PDF metadata extraction uses PyMuPDF if installed (lazy); otherwise falls
back to filename-only entries so the pipeline never hard-fails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from utils.jsonl import write_json

PDF_EXTS = {".pdf"}
TEXT_EXTS = {".txt", ".md", ".docx", ".tex"}


def _pdf_meta(path: Path) -> tuple[str, list[str], int | None]:
    """Best-effort PDF title/author/year from first page text."""
    title, authors, year = "", [], None
    try:
        try:
            import pymupdf as fitz  # PyMuPDF >= 1.24.2 (fitz alias deprecated)
        except ImportError:
            import fitz  # older PyMuPDF
        doc = fitz.open(str(path))
        meta = doc.metadata or {}
        title = meta.get("title") or ""
        authors_raw = meta.get("author") or ""
        if authors_raw:
            authors = [a.strip() for a in re.split(r"[;,]", authors_raw) if a.strip()]
        first_page = doc[0].get_text()[:2000] if doc.page_count else ""
        doc.close()
        if not title:
            lines = [l.strip() for l in first_page.splitlines() if l.strip()]
            if lines:
                title = lines[0][:200]
        m = re.search(r"((?:19|20)\d{2})", first_page)
        if m:
            year = int(m.group(1))
    except Exception:
        pass
    if not title:
        title = path.stem.replace("_", " ").replace("-", " ").title()
    return title, authors, year


def _docx_meta(path: Path) -> tuple[str, list[str], int | None]:
    try:
        from docx import Document
        doc = Document(path)
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        title = paras[0][:200] if paras else path.stem
        year = None
        m = re.search(r"((?:19|20)\d{2})", " ".join(paras[:5]))
        if m:
            year = int(m.group(1))
        return title, [], year
    except Exception:
        return path.stem, [], None


def scan_paths(paths: list[str]) -> list[dict]:
    files: list[Path] = []
    for p in paths:
        path = Path(p).expanduser()
        if path.is_dir():
            files.extend(f for f in sorted(path.rglob("*")) if f.suffix.lower() in PDF_EXTS | TEXT_EXTS)
        elif path.is_file() and path.suffix.lower() in PDF_EXTS | TEXT_EXTS:
            files.append(path)
        elif path.is_file():
            files.append(path)

    out: list[dict] = []
    for f in files:
        if f.suffix.lower() == ".pdf":
            title, authors, year = _pdf_meta(f)
        elif f.suffix.lower() == ".docx":
            title, authors, year = _docx_meta(f)
        else:
            title = f.stem.replace("_", " ").replace("-", " ").title()
            authors, year = [], None
        out.append({
            "title": title,
            "authors": authors,
            "year": year,
            "journal": "",
            "venue": "",
            "venue_type": "other",
            "doi": None,
            "url": str(f),
            "abstract": "",
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
            "source_layer": "local",
            "source": "local_file",
            "source_apis": ["local_file"],
            "tier_score": 0.0,
            "recency_score": 0.0,
            "support_score": None,
            "composite_score": None,
            "local_path": str(f),
        })
    return out


def search_local(query: str, limit: int = 10, paths: list[str] | None = None) -> list[dict]:
    """Dispatch hook — real local scanning needs explicit --paths."""
    if not paths:
        raise RuntimeError("search_local requires explicit --paths (user-provided papers)")
    return scan_paths(paths)[:limit]


def _cli() -> int:
    p = argparse.ArgumentParser(description="Scan local paper files into unified schema")
    p.add_argument("--paths", nargs="+", required=True)
    p.add_argument("--output", "-o", default="local_papers.json")
    args = p.parse_args()
    papers = scan_paths(args.paths)
    write_json(args.output, papers)
    print(f"Local: {len(papers)} papers → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
