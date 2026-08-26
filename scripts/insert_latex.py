"""APA_citation_finder :: insert_latex.py
Stage 8d — LaTeX citation insertion.

* Supports \\cite{}, \\parencite{}, \\textcite{} — the environment is detected
  from the preamble/usages and reused for new citations.
* Never inserts a key already present in the document (no duplicates).
* Existing numbered citations are left untouched (no renumbering).
* thebibliography / \bibliography{} modes are handled by
  update_references.py.

Usage:
  python insert_latex.py paper.tex plan.json --output out.tex
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from utils.jsonl import load_json

SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection|paragraph|chapter)\*?\{([^}]*)\}")
CITE_RE = re.compile(r"\\(?:cite|parencite|textcite|citet|citetext)\w*\*?(\[[^\]]*\])?\{([^}]+)\}")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\])")

# citation commands per style mapping (for agent convenience)
STYLE_TO_COMMAND = {
    "ieee": "\\cite",
    "nature": "\\cite",
    "vancouver": "\\cite",
    "apa": "\\parencite",
    "apa7": "\\parencite",
    "gb-t-7714": "\\cite",
    "gbt7714": "\\cite",
}


def parse_latex(tex_content: str) -> dict:
    document_start = tex_content.find("\\begin{document}")
    document_end = tex_content.find("\\end{document}")
    preamble = tex_content[:document_start] if document_start > 0 else ""
    body_start = document_start + len("\\begin{document}") if document_start > 0 else 0
    body_end = document_end if document_end > 0 else len(tex_content)
    body = tex_content[body_start:body_end]

    sections = []
    matches = list(SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append({"name": name, "start_pos": start + body_start,
                         "end_pos": end + body_start, "content": body[start:end]})

    existing_keys = []
    for m in CITE_RE.finditer(tex_content):
        keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
        existing_keys.extend(keys)

    bib_type = None
    if re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", tex_content, re.S):
        bib_type = "thebibliography"
    elif re.search(r"\\bibliography\{([^}]+)\}", tex_content):
        bib_type = "bibtex"

    return {"preamble": preamble, "body": body, "body_start": body_start,
            "body_end": body_end, "sections": sections,
            "existing_keys": list(set(existing_keys)),
            "bibliography_type": bib_type, "full_text": tex_content}


def detect_citation_command(tex_content: str) -> str:
    """Pick the citation command family in use."""
    for cmd in ("\\textcite", "\\parencite", "\\citeauthor", "\\citet", "\\cite"):
        if cmd in tex_content:
            return cmd.replace("\\", "")
    return "cite"


def _split_sentences_with_offsets(text: str) -> list[tuple[int, int, str]]:
    boundaries = [0]
    for m in SENTENCE_END_RE.finditer(text):
        boundaries.append(m.start())
    boundaries.append(len(text))
    out = []
    for i in range(len(boundaries) - 1):
        seg = text[boundaries[i]:boundaries[i + 1]].strip()
        if seg:
            out.append((boundaries[i], boundaries[i + 1], seg))
    return out


def apply_insertion_plan(tex: str, plan: list[dict], command: str = "cite",
                         dry_run: bool = False) -> tuple[str, list[dict]]:
    """Insert \\cite{key} markers at sentence ends (section-aware).

    plan items: {section, sentence_index, key, claim_id, paper_id}
    Returns (new_text, reports).
    """
    parsed = parse_latex(tex)
    body = parsed["body"]
    existing_keys = set(parsed["existing_keys"])
    reports: list[dict] = []
    insertions: list[tuple[int, str]] = []  # (abs_pos, marker)

    for ins in plan:
        key = ins.get("key", "")
        if not key:
            reports.append({**ins, "status": "skip", "reason": "no bibtex key"})
            continue
        if key in existing_keys:
            reports.append({**ins, "status": "skipped_existing",
                            "reason": "key already cited"})
            continue
        section = ins.get("section", "")
        # locate section content
        target = None
        for sec in parsed["sections"]:
            if section and sec["name"].strip().lower() == str(section).strip().lower():
                target = sec
                break
        if target is None and parsed["sections"]:
            # default: first non-bibliography section (usually Introduction)
            target = parsed["sections"][0]
        if target is None:
            reports.append({**ins, "status": "skip", "reason": "no section found"})
            continue

        sents = _split_sentences_with_offsets(target["content"])
        s_idx = ins.get("sentence_index", 0)
        if s_idx >= len(sents):
            reports.append({**ins, "status": "skip", "reason": "sentence out of range"})
            continue
        start, end, _text = sents[s_idx]
        pos = target["start_pos"] + end
        marker = f"\\{command}{{{key}}}"
        insertions.append((pos, marker))
        reports.append({**ins, "status": "inserted", "position": pos})
        existing_keys.add(key)

    if dry_run:
        return tex, reports

    # apply insertions from the end so positions stay valid
    for pos, marker in sorted(insertions, key=lambda x: -x[0]):
        tex = tex[:pos] + marker + tex[pos:]
    return tex, reports


def _cli() -> int:
    p = argparse.ArgumentParser(description="APA_citation_finder LaTeX citation inserter")
    p.add_argument("tex_file")
    p.add_argument("plan_json", help="plan: {command: cite|parencite|textcite, insertions:[...]}")
    p.add_argument("--output")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    tex = open(args.tex_file, encoding="utf-8").read()
    plan_data = load_json(args.plan_json)
    plan = plan_data.get("insertions") if isinstance(plan_data, dict) else plan_data
    command = (plan_data.get("command") if isinstance(plan_data, dict) else None) \
        or detect_citation_command(tex)

    new_tex, reports = apply_insertion_plan(tex, plan, command, dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0
    out_path = args.output or args.tex_file.replace(".tex", "_cited.tex")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_tex)
    counts: dict[str, int] = {}
    for r in reports:
        counts[r.get("status", "?")] = counts.get(r.get("status", "?"), 0) + 1
    print(json.dumps({"output": out_path, "reports": reports, "counts": counts},
                     ensure_ascii=False, indent=2))
    return 0 if reports else 1


if __name__ == "__main__":
    sys.exit(_cli())
