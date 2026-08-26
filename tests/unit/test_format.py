"""Unit tests: citation formatting (APA variants, IEEE, GB/T, BibTeX,
same-author-same-year, multi-cite combine)."""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from format_citation import (  # noqa: E402
    apa_in_text, apa_combine_in_text, apa_year_suffixes, apa_reference_list,
    format_citation, format_bibtex_entry,
)


def paper(pid, authors, year, title="Some title", venue="Some Journal", doi=None):
    return {"paper_id": pid, "title": title, "authors": authors, "year": year,
            "venue": venue, "doi": doi}


class TestAPAInText(unittest.TestCase):
    def test_one_author(self):
        p = paper("P1", ["Maslow, Abraham"], 1943)
        self.assertEqual(apa_in_text(p), "(Maslow, 1943)")

    def test_two_authors(self):
        p = paper("P2", ["LeCun, Yann", "Bengio, Yoshua"], 2015)
        self.assertEqual(apa_in_text(p), "(LeCun & Bengio, 2015)")

    def test_three_plus_et_al(self):
        p = paper("P3", ["Vaswani, Ashish", "Shazeer, Noam", "Parmar, Niki"], 2017)
        self.assertEqual(apa_in_text(p), "(Vaswani et al., 2017)")

    def test_narrative(self):
        p = paper("P4", ["Maslow, Abraham"], 1943)
        self.assertEqual(apa_in_text(p, narrative=True), "Maslow (1943)")

    def test_unknown_year(self):
        p = paper("P5", ["Doe, John"], None)
        self.assertEqual(apa_in_text(p), "(Doe, n.d.)")


class TestAPASameAuthorSameYear(unittest.TestCase):
    def test_suffixes(self):
        p1 = paper("P1", ["Smith, John"], 2020, title="First paper")
        p2 = paper("P2", ["Smith, John"], 2020, title="Second paper")
        suffixes = apa_year_suffixes([p1, p2])
        self.assertEqual(suffixes["P1"], "a")
        self.assertEqual(suffixes["P2"], "b")

    def test_combine_multi(self):
        joined = apa_combine_in_text(["(Smith, 2020)", "(Lee, 2021)"])
        self.assertEqual(joined, "(Smith, 2020; Lee, 2021)")


class TestReferenceList(unittest.TestCase):
    def test_alphabetical(self):
        papers = [
            paper("P1", ["Vaswani, Ashish", "Shazeer, Noam"], 2017, venue="NeurIPS"),
            paper("P2", ["LeCun, Yann", "Bengio, Yoshua"], 2015, venue="Nature"),
        ]
        text = apa_reference_list(papers)
        self.assertLess(text.index("LeCun"), text.index("Vaswani"))

    def test_doi_rendering(self):
        p = paper("P3", ["LeCun, Yann"], 2015, doi="10.1038/nature14539")
        self.assertIn("https://doi.org/10.1038/nature14539", apa_reference_list([p]))


class TestOtherStyles(unittest.TestCase):
    def test_ieee_numbered(self):
        p = paper("P1", ["Vaswani, Ashish", "Shazeer, Noam", "Parmar, Niki"], 2017,
                  venue="NeurIPS", doi="10.5555/x")
        self.assertTrue(format_citation(p, "ieee", 1).startswith("[1] "))

    def test_gbt7714(self):
        p = paper("P2", ["LeCun, Yann", "Bengio, Yoshua", "Hinton, Geoffrey"], 2015,
                  venue="Nature", doi="10.1038/nature14539")
        out = format_citation(p, "gb-t-7714", 2)
        self.assertTrue(out.startswith("[2] "))
        self.assertIn("DOI:", out)

    def test_nature(self):
        p = paper("P3", ["Vaswani, Ashish", "Shazeer, Noam"], 2017, venue="NeurIPS")
        self.assertTrue(format_citation(p, "nature", 1).startswith("1. "))

    def test_bibtex(self):
        p = paper("P4", ["LeCun, Yann", "Bengio, Yoshua"], 2015,
                  venue="Nature", doi="10.1038/nature14539")
        out = format_bibtex_entry(p, key="lecun2015deep")
        self.assertIn("@article{lecun2015deep,", out)
        self.assertIn("doi", out)


if __name__ == "__main__":
    unittest.main()
