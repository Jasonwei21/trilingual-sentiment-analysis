"""语言自动检测测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trilingual_sentiment.detect import detect_language  # noqa: E402


class TestDetectLanguage(unittest.TestCase):
    def test_zh(self):
        g = detect_language("今天天气不错")
        self.assertEqual(g.code, "zh")
        self.assertGreaterEqual(g.confidence, 0.9)

    def test_ja(self):
        g = detect_language("これは良い天気です")
        self.assertEqual(g.code, "ja")
        self.assertGreaterEqual(g.confidence, 0.9)

    def test_en(self):
        g = detect_language("very good product")
        self.assertEqual(g.code, "en")
        self.assertGreaterEqual(g.confidence, 0.9)

    def test_ja_kana_decisive(self):
        # 含假名即日语，即使夹杂汉字
        g = detect_language("東京タワーは美しい")
        self.assertEqual(g.code, "ja")

    def test_mixed_zh_latin(self):
        g = detect_language("iPhone很好用")
        self.assertEqual(g.code, "zh")
        self.assertLess(g.confidence, 1.0)
        self.assertEqual(g.counts["han"], 3)
        self.assertEqual(g.counts["latin"], 6)

    def test_korean_unknown(self):
        g = detect_language("안녕하세요")
        self.assertEqual(g.code, "unknown")

    def test_digits_unknown(self):
        g = detect_language("12345")
        self.assertEqual(g.code, "unknown")

    def test_empty(self):
        for t in ("", "   ", "！！！"):
            g = detect_language(t)
            self.assertEqual(g.code, "unknown")
            self.assertEqual(g.confidence, 0.0)

    def test_to_dict(self):
        d = detect_language("good").to_dict()
        self.assertEqual(d["code"], "en")
        self.assertIn("confidence", d)
        self.assertIn("counts", d)


if __name__ == "__main__":
    unittest.main()
