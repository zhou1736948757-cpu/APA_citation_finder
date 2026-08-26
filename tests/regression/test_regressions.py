"""Regression tests: behaviors from BOTH old skills must survive the fusion.

From scipilot-cite-skill: title_similarity thresholds, 5 citation styles,
citation numbering (first-appearance), bibtex keys, DOCX/Latex insertion
patterns, Gate 8 no-hallucination audit.
From citation-finder: unified paper schema fields, DOI normalization,
blacklist filtering, tier scoring, source merging.
"""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from utils.text import title_similarity  # noqa: E402
from utils.ids import normalize_doi, make_bibtex_key, assign_citation_numbers  # noqa: E402
from utils.journal import (  # noqa: E402
    compute_tier_score, recency_score, is_blacklisted, filter_blacklisted,
)
from deduplicate import deduplicate  # noqa: E402
from format_citation import (  # noqa: E402
    format_citation, format_bibtex_entry,
)


class TestScipilotRegressions(unittest.TestCase):
    def test_title_similarity_threshold_semantics(self):
        # old skill: 0.85 loose, 0.90 strict
        a = "attention is all you need"
        b = "attention is all you need."
        self.assertGreaterEqual(title_similarity(a, b), 0.90)
        c = "attention mechanisms in neural machine translation"
        self.assertLess(title_similarity(a, c), 0.90)

    def test_five_styles_still_available(self):
        p = {"title": "Deep learning", "authors": ["LeCun, Yann"],
             "year": 2015, "venue": "Nature", "doi": "10.1038/nature14539"}
        for style in ("ieee", "apa", "nature", "vancouver", "gb-t-7714"):
            out = format_citation(p, style, 1)
            self.assertTrue(len(out) > 10, style)

    def test_citation_numbering_first_appearance(self):
        plan = [{"paper_idx": 0, "position": 0},
                {"paper_idx": 1, "position": 1},
                {"paper_idx": 0, "position": 2}]
        numbered = assign_citation_numbers(plan)
        nums = [n["citation_number"] for n in numbered]
        self.assertEqual(nums, [1, 2, 1])  # same paper keeps number 1

    def test_bibtex_key_stable(self):
        p = {"title": "Deep learning", "authors": ["LeCun, Yann"],
             "year": 2015}
        k1 = make_bibtex_key(p)
        k2 = make_bibtex_key(p)
        self.assertEqual(k1, k2)
        self.assertIn("lecun", k1.lower())

    def test_doi_normalization(self):
        self.assertEqual(normalize_doi("HTTPS://DOI.ORG/10.1000/ABC"),
                         "10.1000/abc")
        self.assertIsNone(normalize_doi(None))


class TestCitationFinderRegressions(unittest.TestCase):
    def test_unified_schema_fields(self):
        from search_openalex import _to_unified
        raw = {"title": "T", "publication_year": 2020,
               "authorships": [{"author": {"display_name": "Doe, Jane"}}],
               "doi": "https://doi.org/10.1000/x",
               "host_venue": {"display_name": "J", "type": "journal"},
               "cited_by_count": 5,
               "abstract_inverted_index": {"hello": [0]}}
        u = _to_unified(raw)
        for field in ("title", "authors", "year", "venue", "venue_type",
                      "doi", "abstract", "citation_count", "source_layer",
                      "source", "tier_score", "recency_score"):
            self.assertIn(field, u)
        self.assertEqual(u["authors"], ["Doe, Jane"])

    def test_blacklist_filter(self):
        # venue/publisher-based blacklist match (real CSV entries)
        bad = {"title": "X", "venue": "Oncotarget"}
        bad2 = {"title": "Z", "venue": "Some Journal", "publisher": "MDPI"}
        good = {"title": "Y", "venue": "Nature"}
        self.assertTrue(is_blacklisted(bad))
        self.assertTrue(is_blacklisted(bad2))
        self.assertFalse(is_blacklisted(good))
        kept = filter_blacklisted([bad, bad2, good])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["title"], "Y")

    def test_tier_unknown_default(self):
        self.assertGreaterEqual(compute_tier_score({"venue": "Some Unknown Venue"}), 0.1)

    def test_recency_monotonic(self):
        old = recency_score(2001)
        recent = recency_score(2023)
        self.assertGreater(recent, old)

    def test_source_priority_merge(self):
        a = {"title": "T", "doi": "10.1000/x", "source": "openalex",
             "citation_count": 1}
        b = {"title": "T", "doi": "10.1000/X", "source": "crossref",
             "citation_count": 10}
        merged = deduplicate([a, b])
        self.assertEqual(len(merged), 1)
        self.assertIn("crossref", merged[0]["source"])
        self.assertEqual(sorted(merged[0]["source_apis"]),
                         ["crossref", "openalex"])


def compute_score(p):
    return compute_tier_score(p)


if __name__ == "__main__":
    unittest.main()
