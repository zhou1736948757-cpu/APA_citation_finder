"""APA_citation_finder :: utils/journal.py
Journal/conference quality signals.

IMPORTANT: journal quality is a *quality signal* only — it never dominates
claim support. A Q2 paper that directly supports a claim outranks a Q1 paper
that is merely topically related.

Ported & hardened from citation-finder's tier_utils.py.
"""
from __future__ import annotations

import csv
import datetime
import os
import re
from typing import Any

from .http import rate_limited_request

OPENALEX_SOURCES_URL = "https://api.openalex.org/sources"

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_DIR, "data")
CONF_CSV = os.path.join(DATA_DIR, "priority_journals.csv")
BLACKLIST_CSV = os.path.join(DATA_DIR, "blacklist_journals.csv")

CONFERENCE_TIER_SCORE = 0.8

_conf_lookup: dict | None = None
_blacklist: dict | None = None
_source_cache: dict[str, Any] = {}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _load_conference_lookup() -> dict:
    global _conf_lookup
    if _conf_lookup is not None:
        return _conf_lookup
    lookup = {"abbr": {}, "full": {}}
    if os.path.exists(CONF_CSV):
        try:
            with open(CONF_CSV, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    abbr = (row.get("abbreviation") or "").strip()
                    full = (row.get("full_name") or "").strip()
                    if abbr:
                        lookup["abbr"][_normalize(abbr)] = abbr
                    if full:
                        lookup["full"][_normalize(full)] = full
        except (OSError, IOError):
            pass
    _conf_lookup = lookup
    return lookup


def _load_blacklist() -> dict:
    global _blacklist
    if _blacklist is not None:
        return _blacklist
    bl = {"issn": set(), "name": set(), "publisher": set()}
    if os.path.exists(BLACKLIST_CSV):
        try:
            with open(BLACKLIST_CSV, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    issn = (row.get("issn") or "").strip()
                    name = (row.get("name") or "").strip()
                    publisher = (row.get("publisher") or "").strip()
                    if issn:
                        bl["issn"].add(issn.lower())
                    if name:
                        bl["name"].add(_normalize(name))
                    if publisher:
                        bl["publisher"].add(_normalize(publisher))
        except (OSError, IOError):
            pass
    _blacklist = bl
    return bl


def _is_conference_in_list(venue: str) -> bool:
    if not venue:
        return False
    lookup = _load_conference_lookup()
    norm = _normalize(venue)
    if norm in lookup["abbr"] or norm in lookup["full"]:
        return True
    for full_norm in lookup["full"]:
        if full_norm in norm or norm in full_norm:
            return True
    for abbr_norm in lookup["abbr"]:
        if abbr_norm in norm or norm in abbr_norm:
            return True
    return False


def is_blacklisted(paper: dict) -> bool:
    bl = _load_blacklist()
    issns = []
    if paper.get("issn_l"):
        issns.append(str(paper["issn_l"]))
    issns.extend(paper.get("issn") or [])
    for issn in issns:
        if issn and str(issn).lower() in bl["issn"]:
            return True
    venue = paper.get("venue") or ""
    if venue and _normalize(venue) in bl["name"]:
        return True
    publisher = paper.get("publisher") or ""
    for bl_pub in bl["publisher"]:
        if bl_pub and bl_pub in _normalize(publisher):
            return True
    return False


def filter_blacklisted(papers: list[dict]) -> list[dict]:
    return [p for p in papers if not is_blacklisted(p)]


def _citedness_score(source: dict | None) -> float | None:
    if not source:
        return None
    stats = source.get("summary_stats") or {}
    citedness = stats.get("2yr_mean_citedness") or 0
    if citedness > 10:
        return 0.95
    if citedness > 5:
        return 0.80
    if citedness > 2:
        return 0.60
    if citedness > 0.5:
        return 0.40
    return 0.20


def _lookup_source(params: dict) -> dict | None:
    key = str(sorted(params.items()))
    if key in _source_cache:
        return _source_cache[key]
    data = rate_limited_request(OPENALEX_SOURCES_URL, params=params,
                                min_interval=0.5, max_retries=2)
    src = None
    if data and data.get("results"):
        src = data["results"][0]
    _source_cache[key] = src
    return src


def compute_tier_score(paper: dict, mailto: str | None = None) -> float:
    """Journal/conference quality signal in 0-1. 0.1 = unknown venue.

    - conference whitelist (CCF-A etc.) → 0.8
    - OpenAlex source 2yr_mean_citedness → 0.2 .. 0.95
    - unknown → 0.1
    """
    venue = paper.get("venue") or ""
    venue_type = paper.get("venue_type") or ""

    if venue_type == "conference" or _is_conference_in_list(venue):
        return CONFERENCE_TIER_SCORE

    issn = paper.get("issn_l") or (paper.get("issn") or [None])[0]
    params: dict = {}
    if issn:
        params = {"filter": f"issn:{issn}"}
    elif venue:
        params = {"search": venue, "per_page": 1}
    else:
        return 0.1
    if mailto:
        params["mailto"] = mailto

    source = _lookup_source(params)
    score = _citedness_score(source)
    return score if score is not None else 0.1


def recency_score(year: int | None, current_year: int | None = None) -> float:
    """0-1 recency: <=2y → 1.0; <=5y → 0.8; <=10y → 0.5; <=20y → 0.3; older → 0.1.

    NOTE: recency is a *profile-dependent* signal; for FOUNDATIONAL /
    DEFINITION claims its weight drops to ~0 so original theory papers
    (e.g. Venkatesh 2012) are not displaced by newer secondary sources.
    """
    if current_year is None:
        current_year = datetime.datetime.now().year
    if not year:
        return 0.1
    age = current_year - year
    if age < 0:
        return 1.0
    if age <= 2:
        return 1.0
    if age <= 5:
        return 0.8
    if age <= 10:
        return 0.5
    if age <= 20:
        return 0.3
    return 0.1
