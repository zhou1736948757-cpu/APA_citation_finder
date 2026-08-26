"""Unit tests: claim pipeline (extraction, compound split, need, type,
normalization, query generation). No network. Run from tests/:
    .venv/bin/python -m unittest unit.test_claims -v
"""
import json
import os
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_claims import extract_from_text, _split_compound, _needs_basic_filter  # noqa: E402
from detect_citation_need import classify_need  # noqa: E402
from classify_claims import classify_type  # noqa: E402
from normalize_claim import normalize_claim  # noqa: E402
from generate_queries import generate_queries  # noqa: E402


class TestClaimExtraction(unittest.TestCase):
    def test_simple_sentences(self):
        claims = extract_from_text(
            "First sentence of the document here. Second sentence appears there too.")
        texts = [c["original_text"] for c in claims]
        self.assertIn("First sentence of the document here.", texts)
        self.assertIn("Second sentence appears there too.", texts)

    def test_compound_split(self):
        parts = _split_compound(
            "The Transformer model relies on self-attention mechanisms, and "
            "this design underpins modern language models.")
        self.assertGreaterEqual(len(parts), 2)

    def test_compound_no_enumeration_split(self):
        parts = _split_compound("The system includes feature A, feature B and feature C.")
        self.assertEqual(len(parts), 1)

    def test_chinese_preserved_verbatim(self):
        claims = extract_from_text("生成式人工智能显著提升了学生的学习效果。", "引言")
        self.assertEqual(claims[0]["original_text"], "生成式人工智能显著提升了学生的学习效果。")

    def test_basic_filter_removes_self_reference(self):
        self.assertTrue(_needs_basic_filter("In this paper we propose a new method."))

    def test_offsets_present(self):
        claims = extract_from_text(
            "Hello world this is a long claim statement. Second claim appears here as well.", "sec")
        c = claims[0]
        self.assertIn("char_start", c)
        self.assertIn("char_end", c)
        self.assertIn("paragraph_id", c)
        self.assertIn("sentence_id", c)


class TestCitationNeed(unittest.TestCase):
    def test_required_empirical(self):
        self.assertEqual(
            classify_need("研究表明生成式 AI 提升了学习效果，提升了 23% 的成绩。"),
            "REQUIRED")

    def test_not_needed_self_reference(self):
        self.assertEqual(classify_need("本文提出了一种新的框架。"), "NOT_NEEDED")

    def test_default_recommended(self):
        self.assertEqual(classify_need("该领域近年来发展迅速。"), "RECOMMENDED")


class TestClaimType(unittest.TestCase):
    def test_statistical(self):
        self.assertEqual(classify_type("参与者的准确率提升了 23%。"), "STATISTICAL")

    def test_definition(self):
        self.assertEqual(classify_type("Transformer 是一种基于自注意力机制的架构。"),
                         "DEFINITION")

    def test_method(self):
        self.assertEqual(classify_type("本文提出的算法采用梯度下降进行优化。"), "METHOD")

    def test_empirical_default(self):
        self.assertEqual(classify_type("生成式 AI 对学习结果产生了影响。"), "EMPIRICAL")


class TestNormalize(unittest.TestCase):
    def test_zh_to_en_concepts(self):
        out = normalize_claim("生成式人工智能显著提升了学生的学习效果。")
        self.assertIn("generative", out["search_concepts"][0].lower())

    def test_synonyms(self):
        out = normalize_claim("LLM-based tutoring systems improve outcomes.")
        joined = " ".join(out["search_concepts"])
        self.assertIn("large language model", joined)


class TestQueries(unittest.TestCase):
    def test_four_query_types(self):
        queries = generate_queries("Generative AI significantly improves learning outcomes.")
        kinds = {q["type"] for q in queries}
        self.assertIn("precise", kinds)
        self.assertIn("broad", kinds)
        self.assertIn("synonym", kinds)
        self.assertIn("domain", kinds)

    def test_query_not_equal_claim(self):
        queries = generate_queries("Self-attention underpins modern LLMs.")
        for q in queries:
            if q["type"] != "precise":
                self.assertNotEqual(q["query"], "Self-attention underpins modern LLMs.")

    def test_word_cap(self):
        long = "word " * 60
        for q in generate_queries(long):
            self.assertLessEqual(len(q["query"].split()), 30)


if __name__ == "__main__":
    unittest.main()
