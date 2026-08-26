"""APA_citation_finder :: utils/docx_helpers.py
python-docx paragraph/run/section helpers used by insert_docx.py.
All functions are pure python-docx operations (no string global replace).
"""
from __future__ import annotations

import re
from typing import Any

SENTENCE_END_RE = re.compile(r"(?<=[.!?。！？])\s+(?=\S)")
HEADING_STYLE_RE = re.compile(r"Heading\s*(\d+)", re.I)
SECTION_KEYWORDS = ("reference", "bibliography", "参考文献", "references")

# Existing citation markers we must not duplicate:
#   [1], [3,5], [2-4], (Author, 2020), (Author et al., 2020; B, 2019), [12]
NUMERIC_CITE_RE = re.compile(r"\[\s*\d+(?:\s*[,-]\s*\d+)*\s*\]")
# capture the first number of each marker, for continuation numbering
NUMERIC_DOC_RE = re.compile(r"\[\s*(\d+)(?:\s*[,-]\s*\d+)*\s*\]")
APA_CITE_RE = re.compile(
    r"\([^()]*?[A-Za-z\u4e00-\u9fff][^()]*?(?:19|20)\d{2}[a-z]?(?:[^()]*?;[^()]*?)*\)"
)


def parse_docx_structure(doc) -> dict:
    """Return {paragraphs:[...], sections:[...], existing_references:[...]}."""
    paragraphs = []
    sections: list[dict] = []
    current_section = None

    for i, para in enumerate(doc.paragraphs):
        text = para.text or ""
        style_name = para.style.name if para.style else ""
        heading_match = HEADING_STYLE_RE.match(style_name)
        is_heading = bool(heading_match) or style_name.lower().startswith("title")
        paragraphs.append({
            "index": i,
            "text": text,
            "style": style_name,
            "is_heading": is_heading,
            "heading_level": int(heading_match.group(1)) if heading_match else 0,
        })
        if is_heading and text.strip():
            if current_section:
                current_section["end_index"] = i - 1
                sections.append(current_section)
            current_section = {"name": text.strip(), "start_index": i + 1,
                               "end_index": len(doc.paragraphs) - 1}

    if current_section:
        sections.append(current_section)

    existing_refs = []
    for sec in sections:
        if any(k in sec["name"].lower() for k in APA_KEYWORDS()):
            for p in paragraphs[sec["start_index"]:sec["end_index"] + 1]:
                if p["text"].strip():
                    existing_refs.append(p["text"])

    return {"paragraphs": paragraphs, "sections": sections,
            "existing_references": existing_refs}


def APA_KEYWORDS():
    return ("reference", "bibliography", "参考文献")


def has_existing_citation(text: str) -> bool:
    return bool(APA_CITE_RE.search(text) or NUMERIC_CITE_RE.search(text))


def find_existing_citation_spans(text: str) -> list[tuple[int, int, str]]:
    """Return [(start, end, matched_text)] of existing citation markers."""
    spans = []
    for m in APA_CITE_RE.finditer(text):
        spans.append((m.start(), m.end(), m.group()))
    for m in NUMERIC_CITE_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in spans):
            spans.append((m.start(), m.end(), m.group()))
    spans.sort(key=lambda x: x[0])
    return spans


def append_marker_to_run(run, marker: str) -> None:
    """Append citation marker to a run preserving its formatting."""
    run.text = (run.text or "") + marker


def insert_marker_at_offset(run, offset: int, marker: str) -> None:
    """Insert `marker` at a character offset inside the run.

    Used when a run spans multiple sentences: the citation lands exactly
    at the target sentence's end, preserving the run's formatting.
    """
    text = run.text or ""
    offset = max(0, min(offset, len(text)))
    run.text = text[:offset] + marker + text[offset:]


def insert_marker_before_punctuation(run, marker: str) -> None:
    """Insert `marker` before the sentence-final punctuation of `run.text`.

    e.g. "…improves thinking." → "…improves thinking [3]."
    Keeps the run's formatting (font, bold, italic) because we only change text.
    """
    text = run.text or ""
    stripped = text.rstrip()
    trailing = text[len(stripped):]
    if not stripped:
        run.text = marker + trailing
        return
    if stripped[-1] in ".!?。！？":
        run.text = stripped[:-1] + marker + stripped[-1] + trailing
    else:
        run.text = stripped + marker + trailing


def find_heading_paragraph_index(doc, name: str) -> int | None:
    for i, para in enumerate(doc.paragraphs):
        if (para.text or "").strip().lower() == name.strip().lower():
            return i
    return None


def section_priority(name: str) -> int:
    n = name.lower()
    if "related" in n or "background" in n or "literature" in n:
        return 1
    if "introduction" in n or "intro" in n or "引言" in n:
        return 2
    if "method" in n or "approach" in n or "model" in n or "方法" in n:
        return 3
    if "experiment" in n or "result" in n or "evaluation" in n or "实验" in n:
        return 4
    if "discussion" in n or "conclu" in n or "讨论" in n or "结论" in n:
        return 5
    return 9
