"""APA_citation_finder :: audit_pipeline.py
Final Audit Orchestrator.

Runs:
  * Gate 8A — bibliographic integrity (audit_bibliography.py logic inline)
  * Gate 8B — claim-citation entailment (audit_entailment.py)
  * Evidence-chain completeness — all 7 artifacts exist and are internally
    consistent (claims → search → evidence → verification → support → final)

Writes audit_report.json with overall verdict:
    PASS  — deliverable safe to deliver
    WEAK  — deliverable only with flagged caveats (Academic Standard)
    FAIL  — block delivery

Exit codes: 0=PASS, 2=FAIL-or-WEAK, 3=operational error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from audit_bibliography import (
    audit_document_integrity,
    load_verification_log,
)
from audit_entailment import audit_links
from utils.ids import normalize_doi, paper_id_hash
from utils.jsonl import read_claims, load_json, read_jsonl, write_json

# audit_report.json is deliberately absent from REQUIRED_ARTIFACTS: the
# audit itself produces it, so requiring it beforehand would be self-referential
REQUIRED_ARTIFACTS = {
    "claims.jsonl": "claim extraction",
    "search_log.jsonl": "retrieval log",
    "evidence_log.jsonl": "evidence retrieval",
    "verification_log.jsonl": "paper verification",
    "support_log.jsonl": "support scoring",
    "final_papers.json": "final selection",
}


def check_artifact_chain(run_dir: str) -> dict:
    findings: list[dict] = []
    present: dict[str, bool] = {}
    for name, purpose in REQUIRED_ARTIFACTS.items():
        path = Path(run_dir) / name
        if path.exists() and path.stat().st_size > 0:
            present[name] = True
        else:
            present[name] = False
            findings.append({"level": "FAIL", "check": "artifact_missing",
                             "detail": f"{name} ({purpose})"})
    # internal consistency: every final paper has a verification + evidence record
    try:
        final = load_json(Path(run_dir) / "final_papers.json")
    except Exception:
        final = None
    if final and isinstance(final, dict):
        papers = final.get("papers", [])
        vlog = load_verification_log(str(Path(run_dir) / "verification_log.jsonl"))
        elog = read_jsonl(str(Path(run_dir) / "evidence_log.jsonl"))
        evidence_ids = {e.get("paper_id") for e in elog if e.get("paper_id")}
        for p in papers:
            pid = p.get("paper_id") or paper_id_hash(p)
            if pid not in vlog:
                findings.append({"level": "FAIL", "check": "chain_gap",
                                 "detail": f"{p.get('title', '')[:50]} lacks verification record"})
            if pid not in evidence_ids:
                findings.append({"level": "FAIL", "check": "chain_gap",
                                 "detail": f"{p.get('title', '')[:50]} lacks evidence record"})
    return {"findings": findings, "present": present}


def paper_id_of(p: dict) -> str:
    return paper_id_hash(p)


def run_full_audit(
    run_dir: str,
    document_text: str = "",
    references_texts: list[str] | None = None,
    strict: bool = False,
) -> dict:
    chain = check_artifact_chain(run_dir)
    report: dict[str, Any] = {"run_dir": run_dir, "gates": {}, "chain": chain}

    try:
        final = load_json(Path(run_dir) / "final_papers.json")
    except Exception as e:
        return {"overall": "FAIL", "error": f"final_papers.json unreadable: {e}"}
    if isinstance(final, dict):
        papers = final.get("papers", [])
        links = final.get("links", [])
    else:
        papers = final if isinstance(final, list) else []
        links = []

    # Gate 8A
    vlog = load_verification_log(str(Path(run_dir) / "verification_log.jsonl"))
    gate_a = audit_document_integrity(document_text, papers,
                                      references_texts or [], vlog,
                                      allow_likely_real=not strict)
    report["gates"]["8A_bibliographic"] = {k: gate_a[k] for k in
                                           ("overall", "fails", "weak", "findings")}

    # Gate 8B — independent entailment review
    claims = []
    claims_path = Path(run_dir) / "claims.jsonl"
    if claims_path.exists():
        claims = read_claims(str(claims_path))
    gate_b = audit_links(claims, links, papers)
    report["gates"]["8B_entailment"] = {k: gate_b[k] for k in
                                        ("overall", "counts", "links", "policy")}

    # aggregate
    verdicts = [gate_a["overall"], gate_b["overall"]]
    if any(v == "FAIL" for v in verdicts) or any(f["level"] == "FAIL"
                                                 for f in chain["findings"]):
        overall = "FAIL"
    elif any(v == "WEAK" for v in verdicts) or any(f["level"] == "WEAK"
                                                   for f in chain["findings"]):
        overall = "WEAK"
    else:
        overall = "PASS"
    report["overall"] = overall
    return report


def _cli() -> int:
    p = argparse.ArgumentParser(description="APA_citation_finder final audit pipeline")
    p.add_argument("run_dir", help="run output directory containing the 7 artifacts")
    p.add_argument("--document", help="document text file (for 8A citation scan)")
    p.add_argument("--docx", help="or .docx to extract text")
    p.add_argument("--references", nargs="*", default=[])
    p.add_argument("--strict", action="store_true")
    p.add_argument("--report", "-o", default="audit_report.json")
    args = p.parse_args()

    doc_text = ""
    if args.docx:
        from docx import Document
        doc = Document(args.docx)
        doc_text = "\n".join(pp.text for pp in doc.paragraphs)
    elif args.document:
        doc_text = Path(args.document).read_text(encoding="utf-8")
    refs = [Path(r).read_text(encoding="utf-8") for r in args.references]

    report = run_full_audit(args.run_dir, doc_text, refs, strict=args.strict)
    write_json(args.report, report)
    print(json.dumps({"overall": report["overall"],
                      "8A": report["gates"]["8A_bibliographic"]["overall"],
                      "8B": report["gates"]["8B_entailment"]["overall"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(_cli())
