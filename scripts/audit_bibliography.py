"""APA_citation_finder :: audit_bibliography.py
Gate 8A — Bibliographic Integrity Audit.

Checks the chain (spec §46):
    citation exists in document
        → reference exists
            → paper exists in final_papers
                → verification log entry exists
                    → DOI/metadata consistent

Independent of support scoring. Exit codes: 0=PASS, 2=FAIL, 3=operational error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from utils.ids import normalize_doi, paper_id_hash
from utils.jsonl import load_json, read_jsonl, write_json

NUMERIC_IN_DOC_RE = re.compile(r"\[\s*(\d+(?:\s*[,-]\s*\d+)*)\s*\]")
APA_IN_DOC_RE = re.compile(r"\(([^()]*?(?:19|20)\d{2}[a-z]?(?:[^()]*?;[^()]*?)*)\)")
DOI_IN_TEXT_RE = re.compile(r"doi\.org/([^\s\)\]\},]+)")


def load_verification_log(path: str) -> dict[str, dict]:
    """paper_id -> most recent verification record (last write wins)."""
    out: dict[str, dict] = {}
    for rec in read_jsonl(path):
        if rec.get("event") != "verification":
            continue
        pid = rec.get("paper_id")
        if pid:
            out[pid] = rec
    return out


def extract_doc_citations(doc_text: str) -> dict:
    numeric = [m.group(0) for m in NUMERIC_IN_DOC_RE.finditer(doc_text)]
    apa = [m.group(0) for m in APA_IN_DOC_RE.finditer(doc_text)]
    return {"numeric": numeric, "apa": apa, "count": len(numeric) + len(apa)}


def apa_marker_matches_paper(marker: str, paper: dict) -> bool:
    """Word-boundary match: first-author last name + year in the marker.

    "Smith" must not match "(Smithson, 2020)"; the boundary prevents
    prefix false positives.
    """
    authors = paper.get("authors") or []
    first = authors[0].split(",")[0].strip() if authors else ""
    year = str(paper.get("year") or "")
    if not first:
        return False
    return bool(re.search(rf"\b{re.escape(first)}\b", marker, re.I)
                and year in marker)


def audit_document_integrity(
    doc_text: str,
    final_papers: list[dict],
    references_texts: list[str],
    verification_log: dict[str, dict],
    allow_likely_real: bool = True,
) -> dict:
    acceptable = {"VERIFIED", "LIKELY_REAL"} if allow_likely_real else {"VERIFIED"}
    findings: list[dict] = []

    paper_by_doi: dict[str, dict] = {}
    for p in final_papers:
        doi = normalize_doi(p.get("doi"))
        if doi:
            paper_by_doi[doi] = p

    # 1) every final paper has an acceptable verification log entry
    for p in final_papers:
        pid = p.get("paper_id") or paper_id_hash(p)
        rec = verification_log.get(pid)
        verdict = rec.get("verdict") if rec else None
        if not rec:
            findings.append({"level": "FAIL", "paper": p.get("title"),
                             "check": "verification_log",
                             "detail": "no verification log entry"})
        elif verdict not in acceptable:
            findings.append({"level": "FAIL", "paper": p.get("title"),
                             "check": "verification_verdict",
                             "detail": f"verdict '{verdict}' not acceptable"})

    # 2) DOI consistency: DOIs appearing in references must exist in final_papers
    ref_dois: set[str] = set()
    for ref_text in references_texts:
        for m in DOI_IN_TEXT_RE.finditer(ref_text):
            d = normalize_doi(m.group(1))
            if d:
                ref_dois.add(d)
    for doi in ref_dois:
        if doi not in paper_by_doi:
            findings.append({"level": "FAIL", "check": "reference_doi_orphan",
                             "detail": f"reference lists DOI {doi} not in final_papers"})

    # 3) citation markers in the document body should map to a final paper
    markers = [m.group(0) for m in APA_IN_DOC_RE.finditer(doc_text)]
    markers += [m.group(0) for m in NUMERIC_IN_DOC_RE.finditer(doc_text)]
    for marker in markers:
        found = any(apa_marker_matches_paper(marker, p) for p in final_papers)
        if not found:
            findings.append({"level": "WEAK", "check": "citation_in_document",
                             "detail": f"marker '{marker[:50]}' not mapped to any final paper"})

    # 4) reference entries must be present in the reference section
    if references_texts:
        joined = "\n".join(references_texts).lower()
        for p in final_papers:
            title_frag = (p.get("title") or "")[:60].lower()
            if title_frag and title_frag not in joined:
                findings.append({"level": "WEAK", "check": "reference_entry",
                                 "detail": f"'{title_frag[:40]}...' missing from reference list"})

    fails = [f for f in findings if f["level"] == "FAIL"]
    weaks = [f for f in findings if f["level"] == "WEAK"]
    overall = "FAIL" if fails else ("WEAK" if weaks else "PASS")
    return {"overall": overall, "fails": len(fails), "weak": len(weaks),
            "papers_audited": len(final_papers),
            "findings": findings[:50]}


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gate 8A bibliographic integrity audit")
    p.add_argument("--document", help="extracted document text (.txt/.md)")
    p.add_argument("--docx", help="or .docx to extract text automatically")
    p.add_argument("--papers", required=True, help="final_papers.json")
    p.add_argument("--verification-log", default="verification_log.jsonl")
    p.add_argument("--references", nargs="*", default=[],
                   help="reference-list text files (or extracted docx references)")
    p.add_argument("--report", "-o", default="audit_bibliography.json")
    p.add_argument("--strict", action="store_true", help="LIKELY_REAL not acceptable")
    args = p.parse_args(argv or None)

    data = load_json(args.papers)
    papers = data.get("papers") if isinstance(data, dict) and "papers" in data else (
        data if isinstance(data, list) else [])

    if args.docx:
        from docx import Document
        doc = Document(args.docx)
        doc_text = "\n".join(pp.text for pp in doc.paragraphs)
    elif args.document:
        doc_text = Path(args.document).read_text(encoding="utf-8")
    else:
        doc_text = ""

    refs_text = [Path(r).read_text(encoding="utf-8") for r in args.references]
    vlog = load_verification_log(args.verification_log)
    report = audit_document_integrity(doc_text, papers, refs_text, vlog,
                                      allow_likely_real=not args.strict)
    write_json(args.report, report)
    print(report["overall"], f"(fails={report['fails']}, weak={report['weak']})")
    for f in report["findings"][:20]:
        print(f"  [{f['level']}] {f['check']}: {f.get('detail', '')[:100]}")
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(_cli())
