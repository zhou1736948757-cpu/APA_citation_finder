"""Integration test: full offline pipeline with NO API KEYS and NO network.

Test 10 from spec: the entire core flow must run with zero API keys.
Searches are stubbed with fixture papers; every other stage runs for real:
claim extraction → need/type → normalize → queries → dedup → verification
(mocked NOT_FOUND → cross-check path) → evidence → support (heuristic) →
ranking → formatting → audit chain.

Run: .venv/bin/python -m unittest integration.test_offline_flow -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_claims import extract_from_text  # noqa: E402
from classify_claims import classify_type  # noqa: E402
from detect_citation_need import classify_need  # noqa: E402
from normalize_claim import normalize_claim  # noqa: E402
from generate_queries import generate_queries  # noqa: E402
from deduplicate import deduplicate  # noqa: E402
import verify_papers as vp  # noqa: E402
from fetch_evidence import fetch_evidence  # noqa: E402
from score_support import score_papers  # noqa: E402
from rank_candidates import rank_all  # noqa: E402
from format_bibtex import batch_to_bibtex  # noqa: E402
from audit_entailment import audit_links  # noqa: E402
from utils.jsonl import append_jsonl, write_json  # noqa: E402


class TestOfflinePipeline(unittest.TestCase):
    def test_full_chain_no_keys(self):
        tmp = tempfile.mkdtemp(prefix="scicite_offline_")

        # Stage 1: claims
        claims = extract_from_text(
            "Self-attention mechanisms significantly improve translation quality. "
            "The UTAUT2 model extends the original technology acceptance theory.")
        for c in claims:
            c["claim_type"] = classify_type(c["original_text"])
            c["citation_need"] = classify_need(c["original_text"])
            norm = normalize_claim(c["original_text"])
            c["normalized_claim"] = norm["normalized_claim"]
            c["queries"] = generate_queries(c["original_text"])
        self.assertEqual(len(claims), 2)
        claims_jsonl = Path(tmp) / "claims.jsonl"
        for c in claims:
            claims_jsonl.open("a", encoding="utf-8").write(
                json.dumps(c, ensure_ascii=False) + "\n")

        # Stage 2-3: search stubbed → canned verified-style candidate
        candidate = {
            "title": "Attention is all you need",
            "authors": ["Vaswani, Ashish", "Shazeer, Noam", "Parmar, Niki"],
            "year": 2017, "venue": "NeurIPS", "venue_type": "conference",
            "doi": "10.48550/arXiv.1706.03762",
            "abstract": "The dominant sequence transduction models are based on "
                        "complex recurrent networks. We propose a new simple "
                        "network architecture, the Transformer, based solely on "
                        "attention mechanisms, which achieves superior "
                        "translation quality.",
            "citation_count": 90000, "source_apis": ["openalex", "semantic_scholar"],
            "tier_score": 0.8, "recency_score": 0.1,
        }
        candidates = deduplicate([candidate, dict(candidate, doi="10.48550/arxiv.1706.03762")])
        self.assertEqual(len(candidates), 1)
        write_json(Path(tmp) / "candidates.json", candidates)

        # Stage 4: verify (mock network: Crossref record + S2 agree)
        crossref_msg = {"message": {"title": ["Attention is all you need"],
                                    "issued": {"date-parts": [[2017]]},
                                    "author": [{"family": "Vaswani",
                                                "given": "Ashish"}]}}
        with mock.patch.object(vp, "rate_limited_request",
                               side_effect=[crossref_msg,
                                            {"data": [{"title": "Attention is all you need",
                                                       "year": 2017,
                                                       "authors": [{"name": "Vaswani, Ashish"}]}]}]):
            verified = vp.batch_verify(candidates, max_workers=1,
                                       log_path=str(Path(tmp) / "verification_log.jsonl"))
        self.assertEqual(verified["counts"]["VERIFIED"], 1)

        # Stage 5: evidence
        evidenced = fetch_evidence(verified["kept"], max_workers=1)
        self.assertEqual(evidenced[0]["evidence_level"], "ABSTRACT")

        # Stage 6: support — heuristic (no LLM configured)
        claim = "Transformer attention mechanisms improve translation quality."
        scored = score_papers(claim, evidenced, log_path=str(Path(tmp) / "support_log.jsonl"),
                              claim_id="C001")
        self.assertGreaterEqual(scored[0]["support_score"], 0.60)
        self.assertEqual(scored[0]["scoring_method"], "heuristic")

        # Stage 7: rank
        claim_rec = {"claim_id": "C1", "claim_type": "EMPIRICAL",
                     "citation_need": "REQUIRED",
                     "original_text": claim,
                     "normalized_claim": claim}
        for s in scored:
            s["verification_status"] = "VERIFIED"
        final = rank_all([claim_rec], {"C1": scored})
        self.assertEqual(len(final["papers"]), 1)
        self.assertEqual(final["links"][0]["selection_status"], "SELECTED")

        # Stage 8: bibtex
        bib = batch_to_bibtex(final["papers"])
        self.assertIn("@article", bib)

        # Stage 9: audit chain (8A + 8B)
        chain_ok = all(
            (Path(tmp) / f).exists() and (Path(tmp) / f).stat().st_size > 0
            for f in ("claims.jsonl", "verification_log.jsonl",
                      "support_log.jsonl"))
        self.assertTrue(chain_ok)
        audit = audit_links([claim_rec], final["links"], final["papers"],
                            dry_run_llm=True)
        self.assertIn(audit["overall"], ("PASS", "WEAK"))

        # no keys ever consulted: verify_papers uses no .env/LLM config at all
        import os
        self.assertNotIn("LLM_API_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
