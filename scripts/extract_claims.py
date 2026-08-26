"""APA_citation_finder :: extract_claims.py
Stage 1 — Document parsing + claim extraction.

Input:  text string (--input), or file (.md/.txt/.docx/.tex) via --input-file
Output: claims.json — list of claim records with:
    claim_id, original_text, section, paragraph_id, sentence_id,
    char_start, char_end, source_format, split_from_compound

Features:
  * sentence/paragraph/section/whole-document modes
  * compound-sentence splitting (C001/C002) so one citation cannot
    "support" a whole compound sentence by supporting only one half
  * keeps Chinese originals verbatim (never translated away)
  * optional basic noise filter (self-referential / section-pointer sentences)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from utils.jsonl import write_json, append_jsonl
from utils.text import split_sentences_with_offsets

COMPOUND_SPLITTERS = [
    (r"\s+and\s+", "and"),
    (r"\s+but\s+", "but"),
    (r"\s+while\s+", "while"),
    (r"\s+whereas\s+", "whereas"),
    (r"\s+which\s+", "which"),
]

SELF_REF_RE = re.compile(
    r"^(in this paper|in this work|in this study|in this article|in this section|"
    r"we propose|we present|we introduce|we show|we demonstrate|our approach|"
    r"our method|our contribution|the remainder of|the rest of|the next section|"
    r"the following section|section \d|chapter \d|table \d|figure \d|"
    r"algorithm \d|equation \d|this paper|this study)",
    re.I,
)


def read_input(path: str) -> tuple[str, str]:
    """Return (text, format). Format: docx|tex|md|txt."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "txt"
    if ext == "docx":
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("python-docx required for .docx input (pip install python-docx)")
        doc = Document(path)
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)
        return "\n".join(parts), "docx"
    if ext == "tex":
        with open(path, encoding="utf-8") as f:
            content = f.read()
        body = content
        m = re.search(r"\\begin{document}(.*?)\\end{document}", content, re.S)
        if m:
            body = m.group(1)
        # drop comments and command wrappers, keep body text
        body = re.sub(r"(?<!\\)%.*", "", body)
        body = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", body)
        body = re.sub(r"\s+", " ", body)
        return body, "tex"
    with open(path, encoding="utf-8") as f:
        return f.read(), "md" if ext == "md" else "txt"


def _split_compound(sentence: str) -> list[str]:
    """Split a sentence into independent sub-claims when a coordinating
    conjunction joins two complete clauses (each >= 6 words)."""
    for pattern, _name in COMPOUND_SPLITTERS:
        m = re.search(pattern, sentence)
        if not m:
            continue
        left, right = sentence[:m.start()].strip(), sentence[m.end():].strip()
        if len(left.split()) >= 6 and len(right.split()) >= 6:
            # avoid splitting on enumerations like "A, B and C"
            if left.lower().count(" and ") > 0 or ", and " in left:
                continue
            return [left, right]
    return [sentence]


def _needs_basic_filter(text: str) -> bool:
    """Drop sentences structurally incapable of carrying citations.

    Chinese text has no spaces: judge length by characters, not words.
    """
    t = text.strip()
    if not t:
        return True
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in t)
    if has_cjk:
        if len(t) < 8:
            return True
    elif len(t.split()) < 4:
        return True
    if SELF_REF_RE.search(t):
        return True
    return False


def extract_from_text(
    text: str,
    source_format: str = "text",
    split_compound: bool = True,
    noise_filter: bool = True,
) -> list[dict]:
    """Extract claims from a plain-text body (paragraphs separated by \n)."""
    claims: list[dict] = []
    cidx = 0
    para_offset = 0
    for para_idx, para in enumerate(text.split("\n")):
        if not para.strip():
            para_offset += len(para) + 1
            continue
        for sent in split_sentences_with_offsets(para, base_offset=0):
            sent_text = sent["text"]
            if noise_filter and _needs_basic_filter(sent_text):
                continue
            subs = _split_compound(sent_text) if split_compound else [sent_text]
            sidx = 0
            for sub in subs:
                cidx += 1
                claims.append({
                    "claim_id": f"C{cidx:03d}",
                    "original_text": sub,
                    "normalized_claim": "",
                    "claim_type": "",
                    "citation_need": "",
                    "section": "",
                    "paragraph_id": para_idx,
                    "sentence_id": sidx,
                    "char_start": sent["start"] + para_offset if len(subs) == 1 else None,
                    "char_end": sent["end"] + para_offset if len(subs) == 1 else None,
                    "source_format": source_format,
                    "split_from_compound": len(subs) > 1,
                    "rewrite_permission": "cautious",
                    "queries": [],
                    "search_concepts": [],
                    "synonyms": [],
                })
                sidx += 1
        para_offset += len(para) + 1
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract claims from text/document")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--input-file", help="Path to .md/.txt/.docx/.tex file")
    grp.add_argument("--input", help="Inline text")
    parser.add_argument("--output", "-o", default="claims.jsonl")
    parser.add_argument("--json", action="store_true",
                        help="write a JSON array instead of JSONL")
    parser.add_argument("--no-compound-split", action="store_true",
                        help="disable compound-sentence splitting")
    parser.add_argument("--no-filter", action="store_true",
                        help="disable basic noise filtering")
    args = parser.parse_args()

    if args.input_file:
        text, fmt = read_input(args.input_file)
    else:
        text, fmt = args.input, "text"

    claims = extract_from_text(
        text,
        source_format=fmt,
        split_compound=not args.no_compound_split,
        noise_filter=not args.no_filter,
    )
    if args.json:
        write_json(args.output, claims)
    else:
        for c in claims:
            append_jsonl(args.output, c)
    print(f"Extracted {len(claims)} claims → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
