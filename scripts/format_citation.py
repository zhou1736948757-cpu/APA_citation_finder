"""APA_citation_finder :: format_citation.py
Stage 8 — Citation formatting.

Styles: APA 7th, IEEE, Nature, Vancouver, GB/T 7714-2015.

APA 7 enhancements (spec §36/§73):
  * in-text: (Author, Year) | (Author & Author, Year) | (First et al., Year)
  * same-author-same-year suffix letters (2020a, 2020b)
  * multiple citations: (A, 2020; B, 2021)
  * reference entries sorted alphabetically by first author

Authors come in "Last, First" unified format; helpers accept both
"Last, First" and "First Last".
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any

from utils.ids import make_bibtex_key, normalize_doi
from utils.text import author_initials_first, author_last_initials, normalize_author

# --------------------------------------------------------------------------
# author helpers
# --------------------------------------------------------------------------

def _authors_initials_first(authors: list[str], max_display: int = 6,
                            et_al_threshold: int = 7) -> str:
    if not authors:
        return ""
    formatted = [author_initials_first(a) for a in authors]
    if len(formatted) >= et_al_threshold:
        return f"{formatted[0]}, et al."
    if len(formatted) <= max_display:
        if len(formatted) == 1:
            return formatted[0]
        return ", ".join(formatted[:-1]) + ", and " + formatted[-1]
    return ", ".join(formatted[:max_display]) + ", et al."


def _authors_last_initials_apa(authors: list[str], max_display: int = 20) -> str:
    if not authors:
        return ""
    formatted = [author_last_initials(a) for a in authors]
    if len(formatted) > max_display:
        return ", ".join(formatted[: max_display - 1]) + f", ... {formatted[-1]}"
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


def _authors_nature(authors: list[str]) -> str:
    if not authors:
        return ""
    formatted = [author_last_initials(a).replace(",", "") for a in authors]
    if len(formatted) > 5:
        return f"{formatted[0]} et al"
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + " & " + formatted[-1]


def _authors_vancouver(authors: list[str], max_display: int = 6) -> str:
    if not authors:
        return ""
    formatted = []
    for a in authors:
        rendered = author_last_initials(a).replace(",", "").replace(".", "")
        formatted.append(rendered)
    if len(formatted) > max_display:
        return ", ".join(formatted[:max_display]) + ", et al"
    return ", ".join(formatted)


def _authors_gbt7714(authors: list[str], max_display: int = 3) -> str:
    if not authors:
        return ""
    fmt = []
    for a in authors:
        name = normalize_author(a)
        if any("\u4e00" <= ch <= "\u9fff" for ch in name):
            fmt.append(name)
        else:
            fmt.append(author_last_initials(a).replace(",", "").replace(".", ""))
    if len(fmt) > max_display:
        return ", ".join(fmt[:max_display]) + ", 等"
    return ", ".join(fmt)


# ------------------------------------------------------------------------- full entries

def format_ieee(paper: dict, number: int | None = None) -> str:
    prefix = f"[{number}] " if number is not None else ""
    authors = _authors_initials_first(paper.get("authors") or [])
    title = (paper.get("title", "") or "").rstrip(".")
    venue = paper.get("venue", "") or ""
    year = paper.get("year") or ""
    doi = normalize_doi(paper.get("doi"))
    is_conf = bool(venue) and any(k in venue.lower() for k in
                                  ("conf", "proceedings", "workshop", "symposium"))
    chunks: list[str] = []
    if authors:
        chunks.append(authors + ",")
    chunks.append(f'"{title},"')
    tail_parts: list[str] = []
    if venue:
        tail_parts.append(f"in *{venue}*" if is_conf else f"*{venue}*")
    if year:
        tail_parts.append(str(year))
    if tail_parts:
        chunks.append(", ".join(tail_parts))
    body = " ".join(chunks)
    if doi:
        body = body.rstrip(".") + f", doi: {doi}"
    body = body.rstrip(".") + "."
    return prefix + body


def format_apa7(paper: dict) -> str:
    """APA 7th reference-list entry."""
    authors = _authors_last_initials_apa(paper.get("authors") or [])
    year = paper.get("year") or "n.d."
    title = (paper.get("title") or "").rstrip(".")
    venue = paper.get("venue") or ""
    doi = normalize_doi(paper.get("doi"))
    bits = []
    if authors:
        bits.append(f"{authors}")
    bits.append(f"({year}).")
    bits.append(f"{title}.")
    if venue:
        bits.append(f"*{venue}*.")
    if doi:
        bits.append(f"https://doi.org/{doi}")
    return " ".join(bits)


def format_nature(paper: dict, number: int | None = None) -> str:
    n = f"{number}. " if number is not None else ""
    authors = _authors_nature(paper.get("authors") or [])
    title = (paper.get("title") or "").rstrip(".")
    venue = paper.get("venue") or ""
    year = paper.get("year") or ""
    if year:
        tail = f"*{venue}* ({year})." if venue else f"({year})."
    else:
        tail = f"*{venue}*." if venue else ""
    parts = [n.rstrip()] if n else []
    if authors:
        parts.append(f"{authors}.")
    parts.append(f"{title}.")
    parts.append(tail)
    return " ".join(p for p in parts if p)


def format_vancouver(paper: dict, number: int | None = None) -> str:
    n = f"{number}. " if number is not None else ""
    authors = _authors_vancouver(paper.get("authors") or [])
    title = (paper.get("title") or "").rstrip(".")
    venue = paper.get("venue") or ""
    year = paper.get("year") or ""
    parts = [n.rstrip()] if n else []
    if authors:
        parts.append(f"{authors}.")
    parts.append(f"{title}.")
    if venue:
        parts.append(f"{venue}.")
    if year:
        parts.append(f"{year}.")
    return " ".join(p for p in parts if p)


def format_gbt7714(paper: dict, number: int | None = None) -> str:
    n = f"[{number}] " if number is not None else ""
    authors = _authors_gbt7714(paper.get("authors") or [])
    title = (paper.get("title") or "").rstrip(".")
    venue = paper.get("venue") or ""
    year = paper.get("year") or ""
    doi = normalize_doi(paper.get("doi"))
    parts = []
    if authors:
        parts.append(f"{authors}.")
    parts.append(f"{title}[J].")
    if venue:
        parts.append(f"{venue},")
    if year:
        parts.append(f"{year}.")
    if doi:
        parts.append(f"DOI: {doi}.")
    return n + " ".join(p for p in parts if p)


_FORMATTERS = {
    "ieee": format_ieee,
    "apa7": format_apa7,
    "apa": format_apa7,
    "nature": format_nature,
    "vancouver": format_vancouver,
    "gb-t-7714": format_gbt7714,
    "gbt7714": format_gbt7714,
    "gb-t": format_gbt7714,
}


def format_citation(paper: dict, style: str = "ieee", number: int | None = None) -> str:
    style = (style or "ieee").lower()
    fn = _FORMATTERS.get(style, format_ieee)
    if fn in (format_ieee, format_nature, format_vancouver, format_gbt7714):
        return fn(paper, number)
    return fn(paper)


# --------------------------------------------------------------------------
# APA in-text markers
# --------------------------------------------------------------------------

def apa_first_author(paper: dict) -> str:
    authors = paper.get("authors") or []
    if not authors:
        return "Unknown"
    return author_last_initials(authors[0]).split(",")[0].strip()


def apa_in_text(paper: dict, year_suffix: str = "", narrative: bool = False) -> str:
    """(Author, Year) | (Author & Author, Year) | (First et al., Year).

    narrative=True → "Author and Author (Year)" / "First et al. (Year)".
    """
    authors = paper.get("authors") or []
    year = paper.get("year") or "n.d."
    ys = f"{year}{year_suffix}"
    n = len(authors)

    if n == 0:
        core = f"(Unknown, {ys})" if not narrative else f"Unknown ({ys})"
        return core
    if n == 1:
        name = author_last_initials(authors[0]).split(",")[0].strip()
        return f"({name}, {ys})" if not narrative else f"{name} ({ys})"
    if n == 2:
        a1 = author_last_initials(authors[0]).split(",")[0].strip()
        a2 = author_last_initials(authors[1]).split(",")[0].strip()
        return f"({a1} & {a2}, {ys})" if not narrative else f"{a1} and {a2} ({ys})"
    first = author_last_initials(authors[0]).split(",")[0].strip()
    return f"({first} et al., {ys})" if not narrative else f"{first} et al. ({ys})"


def apa_combine_in_text(parts: list[str]) -> str:
    """Combine multiple in-text markers: (A, 2020; B, 2021)."""
    flat = [p.strip().lstrip("(").rstrip(")") for p in parts]
    return "(" + "; ".join(flat) + ")"


def apa_year_suffixes(papers: list[dict]) -> dict[str, str]:
    """Assign a/b/c suffixes to papers sharing first-author + year (APA rule)."""
    counts: dict[tuple, int] = {}
    out: dict[str, str] = {}
    for p in papers:
        key = (apa_first_author(p), p.get("year") or "n.d.")
        counts[key] = counts.get(key, 0) + 1
    seen: dict[tuple, int] = {}
    for p in papers:
        key = (apa_first_author(p), p.get("year") or "n.d.")
        if counts[key] > 1:
            n = seen.get(key, 0) + 1
            seen[key] = n
            out[p.get("paper_id") or id(p)] = chr(96 + n)  # a, b, c...
        else:
            out[p.get("paper_id") or id(p)] = ""
    return out


def apa_reference_list(papers: list[dict], suffixes: dict[str, str] | None = None) -> str:
    """Alphabetical reference list (by first author last name, then year)."""
    suffixes = suffixes or {}
    def sort_key(p: dict):
        return (apa_first_author(p).lower(), p.get("year") or 9999)
    ordered = sorted(papers, key=sort_key)
    lines = []
    for p in ordered:
        entry = format_apa7(p)
        suf = suffixes.get(p.get("paper_id") or id(p), "")
        if suf:
            # inject suffix into "(year)."
            entry = re.sub(r"\((\d{4}|n\.d\.)\)\.", rf"({p.get('year') or 'n.d.'}{suf}).", entry, count=1)
        lines.append(entry)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# BibTeX
# --------------------------------------------------------------------------

def format_bibtex_entry(paper: dict, key: str | None = None) -> str:
    key = key or make_bibtex_key(paper)
    title = (paper.get("title") or "").replace("{", "\\{").replace("}", "\\}")
    authors = " and ".join(paper.get("authors") or [])
    year = paper.get("year") or ""
    venue = paper.get("venue") or ""
    doi = normalize_doi(paper.get("doi"))
    is_conf = bool(venue) and any(k in venue.lower() for k in
                                  ("conf", "proceedings", "workshop", "symposium"))
    entry_type = "inproceedings" if is_conf else "article"
    venue_key = "booktitle" if is_conf else "journal"

    lines = [f"@{entry_type}{{{key},"]
    lines.append(f"  title     = {{{title}}},")
    if authors:
        lines.append(f"  author    = {{{authors}}},")
    if venue:
        lines.append(f"  {venue_key:9}= {{{venue}}},")
    if year:
        lines.append(f"  year      = {{{year}}},")
    if doi:
        lines.append(f"  doi       = {{{doi}}}")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def _cli() -> int:
    import argparse
    import json
    p = argparse.ArgumentParser(description="APA_citation_finder citation formatter")
    p.add_argument("--style", default="ieee", choices=list(_FORMATTERS.keys()) + ["bibtex"])
    p.add_argument("--input", help="paper JSON file (default stdin)")
    p.add_argument("--number", type=int)
    args = p.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            paper = json.load(f)
    else:
        paper = json.load(sys.stdin)

    if args.style == "bibtex":
        print(format_bibtex_entry(paper))
    else:
        print(format_citation(paper, args.style, args.number))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
