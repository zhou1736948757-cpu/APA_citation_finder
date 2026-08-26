"""Unit tests: dedup + verification gate logic (mocked network)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from deduplicate import deduplicate  # noqa: E402
import verify_papers as vp  # noqa: E402


def paper(doi=None, title="T", year=2020, authors=("Doe, Jane",)):
    return {"title": title, "authors": list(authors), "year": year, "doi": doi}


class TestDedup(unittest.TestCase):
    def test_doi_exact(self):
        a = paper("10.1000/abc", "Same title")
        b = paper("10.1000/ABC", "Same title")
        out = deduplicate([a, b])
        self.assertEqual(len(out), 1)

    def test_doi_prefix_normalized(self):
        a = paper("10.1000/abc", "T")
        b = paper("https://doi.org/10.1000/abc", "T")
        self.assertEqual(len(deduplicate([a, b])), 1)

    def test_fuzzy_title_match(self):
        a = paper(None, "Attention is all you need", 2017, ["Vaswani, Ashish"])
        b = paper(None, "Attention is all you need.", 2017, ["Vaswani, Ashish"])
        self.assertEqual(len(deduplicate([a, b])), 1)

    def test_different_year_not_deduped(self):
        a = paper(None, "Same title", 2015, ["Doe, Jane"])
        b = paper(None, "Same title", 2020, ["Doe, Jane"])
        self.assertEqual(len(deduplicate([a, b])), 2)


class TestVerificationGate(unittest.TestCase):
    """Verify: VERIFIED needs DOI+metadata+second source; CONFLICT rejected."""

    def test_verified_with_second_source(self):
        crossref_msg = {
            "message": {
                "title": ["Attention is all you need"],
                "issued": {"date-parts": [[2017]]},
                "author": [{"family": "Vaswani", "given": "Ashish"}],
            }
        }
        s2_search = {"data": [{"title": "Attention is all you need", "year": 2017,
                               "authors": [{"name": "Vaswani, Ashish"}]}]}
        with mock.patch.object(vp, "rate_limited_request",
                               side_effect=[crossref_msg, s2_search, None]):
            result = vp.verify_by_doi(
                "10.5555/x", "Attention is all you need", 2017,
                ["Vaswani, Ashish"])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertTrue(result["second_source"])

    def test_single_source_not_verified(self):
        crossref_msg = {
            "message": {
                "title": ["Attention is all you need"],
                "issued": {"date-parts": [[2017]]},
                "author": [{"family": "Vaswani", "given": "Ashish"}],
            }
        }
        # second source matches title but NOT the year -> agreement fails
        s2_search = {"data": [{"title": "Attention is all you need", "year": 2019,
                               "authors": [{"name": "Vaswani, Ashish"}]}]}
        with mock.patch.object(vp, "rate_limited_request",
                               side_effect=[crossref_msg, s2_search, None]):
            result = vp.verify_by_doi(
                "10.5555/x", "Attention is all you need", 2017,
                ["Vaswani, Ashish"])
        self.assertEqual(result["status"], "LIKELY_REAL")
        self.assertFalse(result["second_source"])

    def test_fake_doi_rejected(self):
        # DOI does not resolve on Crossref -> UNVERIFIED, no fallback
        with mock.patch.object(vp, "rate_limited_request", return_value=None):
            result = vp.verify_by_doi(
                "10.5555/fake-doi-0001", "Some fabricated paper", 2020,
                ["Fake, Author"])
        self.assertEqual(result["status"], "NOT_FOUND")
        out = vp.verify_paper({"title": "Some fabricated paper", "year": 2020,
                               "doi": "10.5555/fake-doi-0001",
                               "authors": ["Fake, Author"]})
        self.assertEqual(out["verification_status"], "UNVERIFIED")

    def test_conflict_on_year_mismatch(self):
        crossref_msg = {
            "message": {
                "title": ["Attention is all you need"],
                "issued": {"date-parts": [[2017]]},
                "author": [{"family": "Vaswani", "given": "Ashish"}],
            }
        }
        with mock.patch.object(vp, "rate_limited_request", return_value=crossref_msg):
            result = vp.verify_by_doi(
                "10.4857/x", "Attention is all you need", 2020,  # wrong year
                ["Vaswani, Ashish"])
        self.assertEqual(result["status"], "CONFLICT")

    def test_conflict_on_title_mismatch(self):
        crossref_msg = {
            "message": {
                "title": ["Completely different paper"],
                "issued": {"date-parts": [[2017]]},
                "author": [{"family": "Vaswani", "given": "Ashish"}],
            }
        }
        with mock.patch.object(vp, "rate_limited_request", return_value=crossref_msg):
            result = vp.verify_by_doi(
                "10.4857/x", "Attention is all you need", 2017,
                ["Vaswani, Ashish"])
        self.assertEqual(result["status"], "CONFLICT")

    def test_doi_not_found_falls_to_cross_check(self):
        with mock.patch.object(vp, "rate_limited_request", return_value=None):
            result = vp.verify_by_doi(
                "10.9999/nope", "Some title", 2020, ["X, Y"])
        self.assertEqual(result["status"], "NOT_FOUND")

    def test_verify_paper_doi_not_found_rejects(self):
        p = paper("10.9999/nope", "Some title", 2020)
        with mock.patch.object(vp, "rate_limited_request", return_value=None):
            out = vp.verify_paper(p)
        self.assertIn(out["verification_status"], ("UNVERIFIED", "LIKELY_REAL"))


if __name__ == "__main__":
    unittest.main()
