"""生成单文件便携版：内嵌 Vue / AntD / marked / dayjs、判定引擎、词典数据、README 正文。

产物：
- 三语情感极性分析-便携版.html（项目根目录，双击即用，完全离线）
- portable/data.json（供 Node 对拍测试）

用法：python tools/build_portable.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "trilingual_sentiment" / "data"
VENDOR = ROOT / "webapp" / "static" / "vendor"
PLACEHOLDER_RESET = "/*__RESET_CSS__*/"
PLACEHOLDER_VUE = "/*__VUE__*/"
PLACEHOLDER_DAYJS = "/*__DAYJS__*/"
PLACEHOLDER_PLUGINS = "/*__DAYJS_PLUGINS__*/"
PLACEHOLDER_ANTD = "/*__ANTD__*/"
PLACEHOLDER_MARKED = "/*__MARKED__*/"
PLACEHOLDER_ENGINE = "/*__ENGINE__*/"
PLACEHOLDER_DATA = "/*__DATA__*/"
PLACEHOLDER_README = "/*__README__*/"
PLACEHOLDER_APPJS = "/*__APPJS__*/"


def load_csv_dict(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            cells = [c.strip() for c in row]
            if not cells[0] or cells[0].startswith("#"):
                continue
            if cells[0].lower() in ("word", "词语", "語", "単語"):
                continue
            out[cells[0]] = float(cells[1])
    return out


def load_negation(path: Path) -> list[str]:
    words: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            words.extend(w for w in re.split(r"[\s,，、;；/|]+", line) if w)
    return words


def build_data() -> dict:
    data = {}
    for code in ("zh", "ja", "en"):
        data[code] = {
            "lexicon": load_csv_dict(DATA_DIR / f"{code}_sentiment.csv"),
            "negation": load_negation(DATA_DIR / f"{code}_negation.txt"),
            "degree": load_csv_dict(DATA_DIR / f"{code}_degree.csv"),
        }
    return data


def inline_js(path: Path) -> str:
    """JS 文件内容安全内嵌到 <script> 块。"""
    return path.read_text(encoding="utf-8").replace("</script", "<\\/script")


def main() -> None:
    data = build_data()
    template = (ROOT / "portable" / "template.html").read_text(encoding="utf-8")

    plugins = "".join(
        inline_js(VENDOR / f"dayjs.{p}.js")
        for p in ("advancedFormat", "customParseFormat", "localeData",
                  "quarterOfYear", "weekOfYear", "weekYear", "weekday")
    )
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")

    html = (
        template
        .replace(PLACEHOLDER_RESET, (VENDOR / "reset.css").read_text(encoding="utf-8"))
        .replace(PLACEHOLDER_VUE, inline_js(VENDOR / "vue.global.prod.js"))
        .replace(PLACEHOLDER_DAYJS, inline_js(VENDOR / "dayjs.min.js"))
        .replace(PLACEHOLDER_PLUGINS, plugins)
        .replace(PLACEHOLDER_ANTD, inline_js(VENDOR / "antd.min.js"))
        .replace(PLACEHOLDER_MARKED, inline_js(VENDOR / "marked.min.js"))
        .replace(PLACEHOLDER_ENGINE, inline_js(ROOT / "portable" / "engine.js"))
        .replace(PLACEHOLDER_DATA, "const DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";")
        .replace(PLACEHOLDER_README, "window.__README_TEXT__ = " + json.dumps(readme_text, ensure_ascii=False) + ";")
        .replace(PLACEHOLDER_APPJS, inline_js(ROOT / "webapp" / "static" / "app.js"))
    )

    for ph in (PLACEHOLDER_RESET, PLACEHOLDER_VUE, PLACEHOLDER_DAYJS, PLACEHOLDER_PLUGINS,
               PLACEHOLDER_ANTD, PLACEHOLDER_MARKED, PLACEHOLDER_ENGINE,
               PLACEHOLDER_DATA, PLACEHOLDER_README, PLACEHOLDER_APPJS):
        assert ph not in html, f"占位符未替换干净: {ph}"

    out_html = ROOT / "三语情感极性分析-便携版.html"
    out_html.write_text(html, encoding="utf-8")
    (ROOT / "portable" / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    counts = {c: len(d["lexicon"]) for c, d in data.items()}
    print(f"生成: {out_html.name} ({out_html.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"词典: {counts}")


if __name__ == "__main__":
    main()
