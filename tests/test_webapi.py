"""Web 后端 API 测试（Flask test_client，不起真实端口）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import app as webapp  # noqa: E402


class WebApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = webapp.app.test_client()

    def test_index_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("三语情感极性分析台", html)
        self.assertIn("app-analysis", html)   # Vue 挂载点
        self.assertIn("vendor/antd", html)    # Ant Design 本地化

    def test_analyze_zh(self):
        resp = self.client.post("/api/analyze", json={"text": "非常不好"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["language"]["code"], "zh")
        self.assertEqual(data["label"], "负面")
        self.assertLess(data["index"], -10)
        self.assertEqual(data["matched_count"], 1)
        self.assertEqual(data["sentences"][0]["matched"][0]["word"], "好")
        self.assertTrue(data["sentences"][0]["tokens"])

    def test_analyze_en_mixed_sentences(self):
        resp = self.client.post(
            "/api/analyze",
            json={"text": "The camera is good, but the battery is terrible."},
        )
        data = resp.get_json()
        self.assertEqual(data["language"]["code"], "en")
        self.assertLess(data["index"], 0)
        self.assertGreaterEqual(data["sentence_count"], 1)

    def test_analyze_mixed_lang_sentences(self):
        resp = self.client.post(
            "/api/analyze",
            json={"text": "这个非常好。これは良くない。"},
        )
        data = resp.get_json()
        self.assertEqual(data["sentence_count"], 2)
        langs = [s["language"]["code"] for s in data["sentences"]]
        self.assertEqual(langs, ["zh", "ja"])
        self.assertEqual(data["sentences"][0]["label"], "正面")
        self.assertEqual(data["sentences"][1]["label"], "负面")

    def test_analyze_index_scale(self):
        # 纯正面词平均加权 2.0 → +100；纯负面 → -100
        pos = self.client.post("/api/analyze", json={"text": "非常好"}).get_json()
        self.assertAlmostEqual(pos["index"], 100.0, delta=1.0)
        neg = self.client.post("/api/analyze", json={"text": "非常不好"}).get_json()
        self.assertAlmostEqual(neg["index"], -100.0, delta=1.0)

    def test_analyze_neutral(self):
        data = self.client.post("/api/analyze", json={"text": "爱，恨"}).get_json()
        self.assertEqual(data["label"], "中性")
        self.assertAlmostEqual(data["index"], 0.0, delta=1.0)

    def test_analyze_no_match(self):
        data = self.client.post("/api/analyze", json={"text": "玻璃幕墙"}).get_json()
        self.assertEqual(data["label"], "无法判断")
        self.assertIsNone(data["index"])

    def test_analyze_unknown_script(self):
        data = self.client.post("/api/analyze", json={"text": "안녕하세요"}).get_json()
        self.assertEqual(data["language"]["code"], "unknown")
        self.assertEqual(data["label"], "无法判断")

    def test_ping_and_exit(self):
        # 心跳续活
        r = self.client.post("/api/ping", json={"id": "t1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        # sendBeacon 风格（text/plain JSON）也应被识别
        r = self.client.post(
            "/api/exit", data='{"id": "t1"}', content_type="text/plain"
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_exit_unknown_client_ok(self):
        r = self.client.post("/api/exit", json={"id": "never-seen"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_analyze_empty_400(self):
        resp = self.client.post("/api/analyze", json={"text": "   "})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_lexicon_page(self):
        resp = self.client.get("/lexicon")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("词典文件查看", html)      # 页面壳
        self.assertIn("app-lexicon", html)      # Vue 挂载点
        # 词典官方来源信息在 app.js（前端应用）
        appjs = self.client.get("/app.js").get_data(as_text=True)
        self.assertIn("keenage.com", appjs)
        self.assertIn("cl.ecei.tohoku.ac.jp", appjs)
        self.assertIn("mpqa.cs.pitt.edu", appjs)

    def test_api_lexicon(self):
        resp = self.client.get("/api/lexicon/zh_sentiment")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreater(data["count"], 1000)  # 完整版 HowNet 词典
        self.assertEqual(data["file"], "zh_sentiment.csv")
        self.assertTrue(any(e[0] == "好" for e in data["entries"]))

    def test_api_lexicon_negation(self):
        resp = self.client.get("/api/lexicon/ja_negation")
        data = resp.get_json()
        self.assertIn(["ない"], data["entries"])

    def test_api_lexicon_unknown_404(self):
        resp = self.client.get("/api/lexicon/nope")
        self.assertEqual(resp.status_code, 404)

    def test_lexicon_file_download(self):
        resp = self.client.get("/files/lexicon/zh_sentiment.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("好", resp.get_data(as_text=True))

    def test_lexicon_file_reject(self):
        resp = self.client.get("/files/lexicon/app.py")
        self.assertIn(resp.status_code, (403, 404))

    def test_manual_page(self):
        resp = self.client.get("/manual")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("使用指南", html)     # 页面壳
        self.assertIn("app-manual", html)   # Vue 挂载点（md 阅读器）
        self.assertIn("vendor/marked", html)  # 内建 md 阅读器

    def test_manual_download(self):
        resp = self.client.get("/files/readme.md")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("三语情感极性分析台", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
