"""APA_citation_finder :: utils/text.py
Text helpers: sentence splitting, title similarity, keywords, author names.
"""
from __future__ import annotations

import re
from typing import Iterable

try:
    from Levenshtein import ratio as _lev_ratio
except ImportError:
    from difflib import SequenceMatcher

    def _lev_ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()


_STOPWORDS = set(
    """a an the and or but is are was were be been being have has had do does did
    will would could should may might can shall must of in on at to for with from by
    as into during including until against among throughout despite towards upon
    concerning regarding considering than such this that these those which who whom
    whose what when where why how all any both each few more most other some no nor
    not only own same so too very i me my we us our you your he him his she her it
    its they them their however therefore thus while although also propose method
    approach paper present results show study research using based via through over
    under between presented conducted""".split()
)

SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?。！？])\s+(?=[^\s])"          # ASCII/中文句末标点 + 空白
    r"|(?<=[。！？])(?=[^\s])"               # 中文标点后紧跟（无空格）
)


def title_similarity(title1: str, title2: str) -> float:
    """0-1 similarity between two titles (case/space/punctuation-insensitive)."""

    def _norm(s: str) -> str:
        s = (s or "").lower()
        s = re.sub(r"[^\w\s]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    n1, n2 = _norm(title1), _norm(title2)
    if not n1 or not n2:
        return 0.0
    return _lev_ratio(n1, n2)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles . ! ? and Chinese 。！？.

    Keeps the sentence-ending punctuation attached to each sentence.
    """
    if not text or not text.strip():
        return []
    raw = [s.strip() for s in SENTENCE_BOUNDARY_RE.split(text.strip()) if s.strip()]
    merged: list[str] = []
    for frag in raw:
        if merged and len(frag.split()) < 3:
            merged[-1] = merged[-1] + " " + frag
        else:
            merged.append(frag)
    return merged


def split_sentences_with_offsets(text: str, base_offset: int = 0) -> list[dict]:
    """Split and return [{start, end, text}] with absolute char offsets.

    end is exclusive (points just past the sentence). whitespace before the
    next sentence is not included.
    """
    out: list[dict] = []
    pos = 0
    n = len(text)
    while pos < n:
        while pos < n and text[pos].isspace():
            pos += 1
        if pos >= n:
            break
        start = pos
        # advance until sentence boundary
        while pos < n:
            ch = text[pos]
            if ch in ".!?。！？；":
                end = pos + 1
                # swallow trailing closing quotes/brackets
                while end < n and text[end] in "\"')】」』\u201d":
                    end += 1
                out.append({"start": base_offset + start, "end": base_offset + end,
                            "text": text[start:end].strip()})
                pos = end
                break
            pos += 1
        else:
            # no boundary found: rest of text
            out.append({"start": base_offset + start, "end": base_offset + n,
                        "text": text[start:n].strip()})
            break
    return out


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Frequency-based keyword extraction (stopwords removed)."""
    if not text:
        return []
    words = re.findall(r"\b[A-Za-z][A-Za-z\-]{2,}\b", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w in _STOPWORDS or len(w) <= 2:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:top_n]]


def keyword_overlap(text_a: str, text_b: str) -> float:
    """Coverage of A's keywords inside B's keywords (0-1).

    A is the claim: how many of its key concepts appear in the evidence.
    Single-direction coverage avoids penalizing long abstracts the way
    symmetric Dice overlap does.
    """
    def _set(t: str) -> set[str]:
        return set(extract_keywords(t, top_n=50))
    sa, sb = _set(text_a), _set(text_b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa)


def normalize_author(name_or_obj) -> str:
    """Unify an author to 'First Middle Last' string."""
    if isinstance(name_or_obj, str):
        return name_or_obj.strip()
    if isinstance(name_or_obj, dict):
        if name_or_obj.get("name"):
            return str(name_or_obj["name"]).strip()
        given = name_or_obj.get("given", "")
        family = name_or_obj.get("family", "")
        return f"{given} {family}".strip()
    return str(name_or_obj)


def first_author_last_name(authors: Iterable) -> str:
    """Last name of first author (after comma or last token)."""
    authors = list(authors or [])
    if not authors:
        return ""
    name = normalize_author(authors[0])
    if "," in name:
        return name.split(",", 1)[0].strip()
    parts = name.split()
    return parts[-1] if parts else ""


def initials(given_name: str) -> str:
    """'John Quincy' -> 'J. Q.'"""
    parts = re.split(r"[\s\-]+", given_name.strip())
    return " ".join(f"{p[0].upper()}." for p in parts if p)


def author_initials_first(name: str) -> str:
    """'John Smith' -> 'J. Smith'; 'Smith, John' -> 'J. Smith'."""
    name = name.strip()
    if "," in name:
        last, given = [p.strip() for p in name.split(",", 1)]
        return f"{initials(given)} {last}"
    parts = name.split()
    if len(parts) < 2:
        return name
    last = parts[-1]
    given = " ".join(parts[:-1])
    return f"{initials(given)} {last}"


def author_last_initials(name: str) -> str:
    """'John Smith' -> 'Smith, J.'; 'Smith, John' -> 'Smith, J.'"""
    name = name.strip()
    if "," in name:
        last, given = [p.strip() for p in name.split(",", 1)]
        return f"{last}, {initials(given)}"
    parts = name.split()
    if len(parts) < 2:
        return name
    last = parts[-1]
    given = " ".join(parts[:-1])
    return f"{last}, {initials(given)}"


def is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))
