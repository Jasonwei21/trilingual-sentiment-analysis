"""便携版回归测试：构建产物完整性 + Node 引擎与 Python 规则对拍。"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_NAME = "三语情感极性分析-便携版.html"


class TestPortableBuild(unittest.TestCase):
    def test_build_output(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_portable.py")],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        html = ROOT / HTML_NAME
        self.assertTrue(html.exists(), "便携版 HTML 未生成")
        content = html.read_text(encoding="utf-8")
        self.assertNotIn("/*__ENGINE__*/", content)
        self.assertNotIn("/*__DATA__*/", content)
        self.assertIn("PortEngine", content)
        self.assertIn("const DATA", content)
        # 词典数据应内嵌
        self.assertIn("非常", content)
        self.assertIn("素晴らしい", content)

    def test_engine_cases_via_node(self):
        try:
            r = subprocess.run(
                ["node", str(ROOT / "tests" / "portable_cases.js")],
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
        except FileNotFoundError:
            self.skipTest("未安装 Node.js，跳过 JS 引擎对拍")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ALL PASS", r.stdout)


    def test_portable_dom_smoke(self):
        """jsdom 真实执行 Vue/AntD/marked 全链路（需 node + jsdom）。"""
        try:
            r = subprocess.run(
                ["node", str(ROOT / "tests" / "portable_dom_test.mjs")],
                capture_output=True, text=True, cwd=ROOT,
            )
        except FileNotFoundError:
            self.skipTest("未安装 Node.js，跳过 DOM 冒烟")
        if "Cannot find package" in (r.stdout + r.stderr):
            self.skipTest("未安装 jsdom（npm install jsdom），跳过 DOM 冒烟")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("DOM SMOKE ALL PASS", r.stdout)


if __name__ == "__main__":
    unittest.main()
