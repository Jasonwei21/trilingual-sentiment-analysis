"""三语情感极性判定工具测试。

覆盖：极性判定、否定反转、程度加权、空输入、未知语言、词典缺失等。
运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trilingual_sentiment import (  # noqa: E402
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    LABEL_UNKNOWN,
    SentimentAnalyzer,
    SentimentLexicon,
)
from trilingual_sentiment.analyzer import LanguageProfile  # noqa: E402
from trilingual_sentiment.rules import DegreeRule, NegationRule  # noqa: E402
from trilingual_sentiment.tokenizers import build_tokenizer  # noqa: E402

DATA_DIR = ROOT / "trilingual_sentiment" / "data"


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.az = SentimentAnalyzer()


class TestBasicPolarity(BaseCase):
    def test_zh_positive(self):
        r = self.az.analyze("好", "zh")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertGreater(r.score, 0)
        self.assertEqual(len(r.matched), 1)
        self.assertEqual(r.matched[0].word, "好")
        self.assertGreater(r.matched[0].base_score, 0)

    def test_zh_negative(self):
        r = self.az.analyze("讨厌", "zh")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertLess(r.score, 0)

    def test_en_positive(self):
        r = self.az.analyze("good", "en")
        self.assertEqual(r.label, LABEL_POSITIVE)

    def test_ja_positive(self):
        r = self.az.analyze("嬉しい", "ja")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertGreater(r.score, 0)

    def test_zh_mixed_neutral(self):
        r = self.az.analyze("爱，恨", "zh")
        self.assertEqual(r.label, LABEL_NEUTRAL)
        self.assertAlmostEqual(r.score, 0.0, places=6)
        self.assertEqual(len(r.matched), 2)

    def test_unknown_words(self):
        r = self.az.analyze("玻璃幕墙", "zh")
        self.assertEqual(r.label, LABEL_UNKNOWN)
        self.assertEqual(r.matched, [])
        self.assertEqual(r.score, 0.0)


class TestNegation(BaseCase):
    def test_zh_negation_prefix(self):
        r = self.az.analyze("不好", "zh")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertEqual(r.matched[0].word, "好")
        self.assertTrue(r.matched[0].negated)
        self.assertAlmostEqual(r.matched[0].weighted_score, -r.matched[0].base_score, places=6)

    def test_zh_negation_window(self):
        r = self.az.analyze("不觉得好", "zh")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertTrue(any(m.word == "好" and m.negated for m in r.matched))

    def test_en_not_good(self):
        r = self.az.analyze("not good", "en")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertTrue(r.matched[0].negated)
        self.assertEqual(r.matched[0].negation_trigger, "not")

    def test_en_double_negation(self):
        r = self.az.analyze("not bad", "en")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertTrue(r.matched[0].negated)
        self.assertAlmostEqual(r.matched[0].weighted_score, 1.5, places=6)  # bad -1.5 反转

    def test_en_contraction(self):
        r = self.az.analyze("isn't good", "en")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertTrue(r.matched[0].negated)

    def test_ja_yokunai(self):
        r = self.az.analyze("良くない", "ja")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertAlmostEqual(r.score, -1.0, places=6)
        self.assertEqual(len(r.matched), 1)
        self.assertTrue(r.matched[0].negated)

    def test_ja_suffix_negation(self):
        r = self.az.analyze("嬉しくない", "ja")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertTrue(r.matched[0].negated)


class TestDegree(BaseCase):
    def test_zh_degree(self):
        r = self.az.analyze("非常好", "zh")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertAlmostEqual(r.matched[0].weighted_score, 3.0, places=6)  # 好 +1.5 × 非常 2.0
        self.assertEqual(r.matched[0].degree, "非常")
        self.assertAlmostEqual(r.matched[0].degree_weight, 2.0, places=6)

    def test_zh_degree_negation(self):
        r = self.az.analyze("非常不好", "zh")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertAlmostEqual(r.score, -3.0, places=6)

    def test_zh_dampen_degree(self):
        r = self.az.analyze("稍微好", "zh")
        self.assertAlmostEqual(r.matched[0].weighted_score, 0.75, places=6)  # 1.5 × 0.5

    def test_zh_degree_compound(self):
        # 「太差」被切为一个词时：程度前缀 + 词干拆分（太 + 差）
        r = self.az.analyze("太差", "zh")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        m = r.matched[0]
        self.assertEqual(m.word, "差")
        self.assertTrue(m.negated is False)
        self.assertEqual(m.degree, "太")
        self.assertAlmostEqual(m.weighted_score, -1.8, places=6)  # 差 -1.0 × 太 1.8

    def test_zh_negation_degree_compound(self):
        # 不太好 → 否定 + 程度 + 词干
        r = self.az.analyze("不太好", "zh")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertAlmostEqual(r.score, -1.5, places=6)

    def test_en_degree(self):
        r = self.az.analyze("very good", "en")
        self.assertAlmostEqual(r.matched[0].weighted_score, 1.5, places=6)

    def test_en_degree_negation(self):
        r = self.az.analyze("not very good", "en")
        self.assertEqual(r.label, LABEL_NEGATIVE)
        self.assertAlmostEqual(r.score, -1.5, places=6)
        m = r.matched[0]
        self.assertTrue(m.negated)
        self.assertEqual(m.degree, "very")
        self.assertAlmostEqual(m.degree_weight, 1.5, places=6)

    def test_ja_degree(self):
        r = self.az.analyze("とても嬉しい", "ja")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertAlmostEqual(r.matched[0].weighted_score, 1.0 * 1.6, places=6)  # 嬉しい +1.0 × 1.6


class TestEdgeCases(BaseCase):
    def test_empty_input_raises(self):
        for bad in ("", "   ", "\n\t"):
            with self.assertRaises(ValueError):
                self.az.analyze(bad, "zh")

    def test_unknown_language(self):
        r = self.az.analyze("good", "fr")
        self.assertEqual(r.label, LABEL_UNKNOWN)
        self.assertEqual(r.matched, [])
        self.assertTrue(any("未知语言代码" in w for w in r.warnings))
        self.assertEqual(r.language, "fr")

    def test_language_code_case_insensitive(self):
        r = self.az.analyze("good", "EN")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertEqual(r.language, "en")

    def test_empty_lexicon_language(self):
        tok, _ = build_tokenizer("en", {"good"})
        profile = LanguageProfile(
            code="zz",
            name="test",
            lexicon=SentimentLexicon("zz", "empty"),
            negation_rule=NegationRule({"not"}),
            degree_rule=DegreeRule({"very": 1.5}),
            tokenizer=tok,
        )
        self.az.register_language(profile)
        try:
            r = self.az.analyze("good", "zz")
        finally:
            self.az._profiles.pop("zz", None)  # 不污染其他用例
        self.assertEqual(r.label, LABEL_UNKNOWN)
        self.assertTrue(any("词典" in w for w in r.warnings))

    def test_lexicon_file_missing(self):
        with self.assertRaises(FileNotFoundError):
            SentimentLexicon.from_csv(ROOT / "tests" / "no_such_file.csv")

    def test_lexicon_csv_load(self):
        lex = SentimentLexicon.from_csv(DATA_DIR / "zh_sentiment.csv", language="zh")
        self.assertGreater(len(lex), 1000)  # 完整版 HowNet 词典
        self.assertIn("好", lex)
        self.assertEqual(lex.get("好"), 1.5)  # 正面情感类 +1.5

    def test_lexicon_json_roundtrip(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "lex.json"
            p.write_text(json.dumps({"happy": 1.5, "sad": -1.5}), encoding="utf-8")
            lex = SentimentLexicon.from_json(p, language="en")
        self.assertEqual(lex.get("happy"), 1.5)
        self.assertEqual(lex.get("sad"), -1.5)

    def test_match_fields_present(self):
        r = self.az.analyze("不好", "zh")
        m = r.matched[0]
        self.assertIsInstance(m.base_score, float)
        self.assertIsInstance(m.weighted_score, float)
        d = r.to_dict()
        self.assertEqual(d["label"], LABEL_NEGATIVE)
        self.assertEqual(len(d["matched"]), 1)
        self.assertIn("base_score", d["matched"][0])
        self.assertIn("weighted_score", d["matched"][0])

    def test_add_word_extension(self):
        az = SentimentAnalyzer()
        az.add_word("en", "zzzawesome", 2.0)
        r = az.analyze("zzzawesome", "en")
        self.assertEqual(r.label, LABEL_POSITIVE)
        self.assertAlmostEqual(r.score, 2.0, places=6)


class TestRuleLoaders(unittest.TestCase):
    def test_load_negation_words(self):
        from trilingual_sentiment.rules import load_negation_words

        words = load_negation_words(DATA_DIR / "zh_negation.txt")
        self.assertIn("不", words)
        self.assertIn("没有", words)

    def test_load_degree_weights(self):
        from trilingual_sentiment.rules import load_degree_weights

        weights = load_degree_weights(DATA_DIR / "zh_degree.csv")
        self.assertAlmostEqual(weights["非常"], 2.0, places=6)
        self.assertAlmostEqual(weights["稍微"], 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
