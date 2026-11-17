"""三语情感极性分析台 —— Web 后端。

路由：
- GET  /            前端页面
- POST /api/analyze 规则分析：自动识别语言 → 自动分词 → 计算 -100~100 极性分

启动：python webapp/app.py --open   →   http://127.0.0.1:8765（--open 自动打开浏览器）
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

WEBAPP_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # PyInstaller 打包运行：资源在 _MEIPASS（onedir 下即 _internal）
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    WEBAPP_DIR = ROOT / "webapp"
else:
    ROOT = WEBAPP_DIR.parent
for p in (str(ROOT), str(WEBAPP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

from trilingual_sentiment import (  # noqa: E402
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    LABEL_UNKNOWN,
    SentimentAnalyzer,
)
from trilingual_sentiment.detect import detect_language  # noqa: E402

# 打包为无窗口（console=False）时 stdout/stderr 可能为 None，兜底避免 print 崩溃
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

app = Flask(__name__, static_folder=str(WEBAPP_DIR / "static"))
analyzer = SentimentAnalyzer()

SUPPORTED_LANGS = ("zh", "ja", "en")
# |index| <= 该阈值时视为「中性」（弱倾向）
NEUTRAL_BAND = 10.0
# 极性分 = 匹配词平均加权分 / 2.0 截断到 [-1,1] 再乘 100
SCORE_UNIT = 2.0

_SENT_SPLIT_RE = re.compile(r"[。！？!?]+|(?<=\.)\s+|[\n；;]+")


def split_sentences(text: str) -> list[str]:
    """按中英日句末标点分句（保留非空句）。"""
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text) if p and p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def to_index(weighted_scores: list[float]) -> float | None:
    """匹配词加权分 → -100~100 整体倾向分；无匹配词返回 None。"""
    if not weighted_scores:
        return None
    mean = sum(weighted_scores) / len(weighted_scores)
    return round(max(-100.0, min(100.0, mean / SCORE_UNIT * 100.0)), 1)


def label_from_index(index: float | None) -> str:
    if index is None:
        return LABEL_UNKNOWN
    if index > NEUTRAL_BAND:
        return LABEL_POSITIVE
    if index < -NEUTRAL_BAND:
        return LABEL_NEGATIVE
    return LABEL_NEUTRAL


def analyze_text(text: str) -> dict:
    """整体分析：逐句自动检测语言并判定，聚合为 -100~100 极性分。"""
    overall_guess = detect_language(text)
    sentences: list[dict] = []
    all_weighted: list[float] = []
    total_score = 0.0
    matched_count = 0

    for sent in split_sentences(text):
        guess = detect_language(sent)
        if guess.code not in SUPPORTED_LANGS:
            sentences.append(
                {
                    "text": sent,
                    "language": guess.to_dict(),
                    "label": LABEL_UNKNOWN,
                    "index": None,
                    "score": 0.0,
                    "matched": [],
                    "tokens": [],
                    "warnings": ["无法识别该句语言（仅支持中文/日语/英语）"],
                }
            )
            continue

        explained = analyzer.explain(sent, guess.code)
        weighted = [m["weighted_score"] for m in explained["matched"]]
        all_weighted.extend(weighted)
        total_score += explained["score"]
        matched_count += len(explained["matched"])
        sent_index = to_index(weighted)
        sentences.append(
            {
                "text": sent,
                "language": guess.to_dict(),
                "label": label_from_index(sent_index),
                "index": sent_index,
                "score": round(explained["score"], 4),
                "matched": explained["matched"],
                "tokens": explained["tokens"],
                "warnings": explained["warnings"],
            }
        )

    index = to_index(all_weighted)
    return {
        "text": text,
        "language": overall_guess.to_dict(),
        "index": index,
        "label": label_from_index(index),
        "score": round(total_score, 4),
        "matched_count": matched_count,
        "sentence_count": len(sentences),
        "sentences": sentences,
    }


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------- 词典查看 / 下载（供核验与论文复现）----------
LEXICON_FILES = {
    "zh_sentiment": "zh_sentiment.csv",
    "ja_sentiment": "ja_sentiment.csv",
    "en_sentiment": "en_sentiment.csv",
    "zh_negation": "zh_negation.txt",
    "ja_negation": "ja_negation.txt",
    "en_negation": "en_negation.txt",
    "zh_degree": "zh_degree.csv",
    "ja_degree": "ja_degree.csv",
    "en_degree": "en_degree.csv",
}
_lexicon_cache: dict[str, list] = {}


def _load_lexicon_entries(key: str) -> list:
    """解析词典文件为 [[word, score], ...] 或 [[word], ...]（带缓存）。"""
    if key in _lexicon_cache:
        return _lexicon_cache[key]
    fname = LEXICON_FILES[key]
    path = ROOT / "trilingual_sentiment" / "data" / fname
    entries: list = []
    if fname.endswith(".csv"):
        for row in csv.reader(path.read_text(encoding="utf-8-sig").splitlines()):
            if not row:
                continue
            w = row[0].strip()
            if not w or w.startswith("#") or w.lower() == "word":
                continue
            try:
                entries.append([w, float(row[1])])
            except (IndexError, ValueError):
                continue
    else:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                entries.extend([[w] for w in re.split(r"[\s,，、;；/|]+", line) if w])
    _lexicon_cache[key] = entries
    return entries


@app.get("/lexicon")
def lexicon_page():
    return send_from_directory(app.static_folder, "lexicon.html")


@app.get("/api/lexicon/<key>")
def api_lexicon(key: str):
    if key not in LEXICON_FILES:
        return jsonify({"error": f"未知词典: {key}"}), 404
    entries = _load_lexicon_entries(key)
    return jsonify({"key": key, "file": LEXICON_FILES[key], "count": len(entries), "entries": entries})


@app.get("/files/lexicon/<path:filename>")
def lexicon_file(filename: str):
    allowed = set(LEXICON_FILES.values())
    if filename not in allowed:
        return jsonify({"error": "不允许下载该文件"}), 403
    return send_from_directory(
        ROOT / "trilingual_sentiment" / "data", filename, as_attachment=True
    )


# ---------- 前端静态资源（Vue / AntD / marked 本地化，离线可用）----------
@app.get("/app.js")
def app_js():
    return send_from_directory(app.static_folder, "app.js")


@app.get("/vendor/<path:filename>")
def vendor_file(filename: str):
    return send_from_directory(Path(app.static_folder) / "vendor", filename)


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico")


# ---------- 使用指南（Vue + marked 内建 md 阅读器，/files/readme.md 提供正文）----------
@app.get("/manual")
def manual_page():
    return send_from_directory(app.static_folder, "manual.html")


@app.get("/files/readme.md")
def readme_file():
    return send_from_directory(ROOT, "README.md", as_attachment=True)


# ---------- 心跳与自动退出（打包版：关闭浏览器标签页即退出） ----------
# 每个标签页持有独立 client_id：/api/ping 续活，关闭标签页时 sendBeacon /api/exit。
# 仅当所有标签页都关闭（或浏览器崩溃静默 5 分钟）服务才退出；刷新/页内跳转不受影响。
AUTO_EXIT = os.environ.get("WB_AUTO_EXIT", "").strip().lower() in ("1", "true", "yes") or (
    getattr(sys, "frozen", False)
    and not os.environ.get("WB_NO_AUTO_EXIT", "").strip()
)

_clients = {}  # client_id -> 最近一次 ping 的时间戳
_exit_timer = [None]


def _schedule_exit(delay: float = 5.0) -> None:
    """延迟退出；期间任何 ping 可取消（防止刷新/跳页误杀）。"""
    import threading

    def _bye() -> None:
        if not _clients:  # 期间确无任何标签页回来
            print("浏览器标签页已关闭，服务自动退出。")
            os._exit(0)

    if _exit_timer[0] is not None:
        _exit_timer[0].cancel()
    t = threading.Timer(delay, _bye)
    t.daemon = True
    t.start()
    _exit_timer[0] = t


def _req_json() -> dict:
    """解析请求体：application/json 或 sendBeacon 的 text/plain JSON。"""
    data = request.get_json(silent=True)
    if data is not None:
        return data
    try:
        import json

        return json.loads(request.get_data(as_text=True) or "{}") or {}
    except Exception:
        return {}


@app.post("/api/ping")
def api_ping():
    import time

    data = _req_json()
    cid = str(data.get("id") or "default")
    _clients[cid] = time.time()
    if _exit_timer[0] is not None:
        _exit_timer[0].cancel()
        _exit_timer[0] = None
    return {"ok": True}


@app.post("/api/exit")
def api_exit():
    data = _req_json()
    cid = str(data.get("id") or "default")
    _clients.pop(cid, None)
    if AUTO_EXIT and not _clients:
        _schedule_exit()
        return {"ok": True, "exiting": True}
    return {"ok": True, "exiting": False}


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "输入文本不能为空"}), 400
    return jsonify(analyze_text(text))


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    preferred = int(os.environ.get("PORT", "8765"))
    frozen = getattr(sys, "frozen", False)

    # 端口被占用时自动向后偏移
    import socket

    port = preferred
    for candidate in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, candidate)) != 0:
                port = candidate
                break

    url = f"http://{host}:{port}"
    print(f"三语情感极性分析台: {url}")
    if AUTO_EXIT:
        print("关闭浏览器标签页即自动退出服务。")

        import threading
        import time

        def _watchdog() -> None:
            # 兜底：浏览器崩溃/被强杀时，无任何客户端持续 5 分钟后自动退出。
            # 「持续无客户端」而非「启动满 5 分钟」：休眠唤醒后客户端会立刻续活，避免误杀。
            empty_since = None
            while True:
                time.sleep(5)
                now = time.time()
                for cid in list(_clients):
                    if now - _clients[cid] > 300:
                        _clients.pop(cid, None)
                if _clients:
                    empty_since = None
                else:
                    if empty_since is None:
                        empty_since = now
                    elif now - empty_since > 300:
                        os._exit(0)

        threading.Thread(target=_watchdog, daemon=True).start()
    else:
        print("关闭本窗口即可停止服务。")
    # --open、OPEN_BROWSER=1 或打包运行时自动打开浏览器（WB_NO_BROWSER=1 可抑制）
    if (
        ("--open" in sys.argv or frozen
         or os.environ.get("OPEN_BROWSER", "").strip().lower() in ("1", "true", "yes"))
        and not os.environ.get("WB_NO_BROWSER", "").strip()
    ):
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
