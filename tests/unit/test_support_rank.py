"""Unit tests: support scoring rubric, metadata cap, ranking profiles."""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from score_support import (  # noqa: E402
    level_from_score, cap_metadata_only, score_paper, evaluate_heuristic,
)
from rank_candidates import (  # noqa: E402
    profile_for, rank_for_claim, composite, DEFAULT_SUPPORT_THRESHOLD,
)


class TestRubric(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(level_from_score(0.95), "DIRECT")
        self.assertEqual(level_from_score(0.80), "DIRECT")
        self.assertEqual(level_from_score(0.65), "PARTIAL")
        self.assertEqual(level_from_score(0.45), "BACKGROUND")
        self.assertEqual(level_from_score(0.10), "INSUFFICIENT_EVIDENCE")


class TestMetadataCap(unittest.TestCase):
    def test_cap_metadata_only(self):
        self.assertAlmostEqual(cap_metadata_only(0.9, "AI improves learning"), 0.74)

    def test_metadata_claim_exempt(self):
        score = cap_metadata_only(0.9, "This paper was published in 2020.")
        self.assertAlmostEqual(score, 0.9)

    def test_scoring_metadata_only_capped(self):
        paper = {"title": "Study on AI", "year": 2023, "venue": "X",
                 "evidence_level": "METADATA_ONLY", "evidence_text": "",
                 "abstract": "", "doi": None}
        out = score_paper("AI improves learning", paper, {})
        self.assertLessEqual(out["support_score"], 0.74)


class TestHeuristic(unittest.TestCase):
    def test_matching_abstract_scores_higher(self):
        claim = "transformer attention improves translation quality"
        match = {"evidence_level": "ABSTRACT",
                 "evidence_text": "We show that transformer attention substantially "
                                  "improves translation quality on benchmark datasets."}
        unrelated = {"evidence_level": "ABSTRACT",
                     "evidence_text": "We study soil moisture dynamics in arid "
                                      "grassland ecosystems under climate change."}
        r_match = evaluate_heuristic(claim, match)
        r_unrelated = evaluate_heuristic(claim, unrelated)
        self.assertGreater(r_match["support_score"], r_unrelated["support_score"])
        self.assertGreater(r_match["support_score"], 0.5)

    def test_no_abstract_metadata_only(self):
        p = {"evidence_level": "METADATA_ONLY", "evidence_text": ""}
        r = evaluate_heuristic("anything", p)
        self.assertEqual(r["support_level"], "INSUFFICIENT_EVIDENCE")


class TestRanking(unittest.TestCase):
    def test_below_threshold_rejected(self):
        papers = [
            {"paper_id": "P1", "title": "A", "support_score": 0.55,
             "verification_status": "VERIFIED", "authors": ["A, X"], "venue": "J"},
            {"paper_id": "P2", "title": "B", "support_score": 0.85,
             "verification_status": "VERIFIED", "authors": ["B, X"], "venue": "K"},
        ]
        selected, rejected = rank_for_claim(
            papers, {"claim_type": "EMPIRICAL", "citation_need": "REQUIRED"})
        self.assertEqual([p["paper_id"] for p in selected], ["P2"])
        self.assertEqual([p["paper_id"] for p in rejected], ["P1"])

    def test_unverified_never_selected(self):
        papers = [
            {"paper_id": "P1", "support_score": 0.95,
             "verification_status": "UNVERIFIED", "authors": [], "venue": "", "year": 2020},
        ]
        selected, _ = rank_for_claim(papers, {"claim_type": "EMPIRICAL"})
        self.assertEqual(selected, [])

    def test_profiles(self):
        p = profile_for("THEORETICAL", "REQUIRED")
        self.assertGreater(p["originality"], p["recency"])
        p2 = profile_for("METHOD", "REQUIRED")
        self.assertGreater(p2["method_authority"], 0.3)

    def test_per_claim_limit(self):
        papers = [
            {"paper_id": f"P{i}", "support_score": 0.9,
             "verification_status": "VERIFIED", "authors": [f"A{i}"],
             "venue": f"V{i}", "year": 2020}
            for i in range(5)
        ]
        selected, rejected = rank_for_claim(
            papers, {"claim_type": "EMPIRICAL", "citation_need": "REQUIRED"},
            per_claim=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(len(rejected), 3)


if __name__ == "__main__":
    unittest.main()
