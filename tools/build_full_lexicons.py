"""构建完整版三语情感词典（论文用）。

来源（原始文件保存在 dictionaries/，便于溯源引用）：
- 中文：知网 HowNet「情感分析用词语集(beta 版)」四类词语集
  正面情感 +1.5 / 负面情感 -1.5 / 正面评价 +1.0 / 负面评价 -1.0
- 日语：単語感情極性対応表（日本語評価極性辞書）
  pn.csv.m3.120408.trim（名词语）+ wago.121808.pn（用言）p→+1.0 / n→-1.0
- 英语：MPQA Subjectivity Lexicon（subjclueslen1-HLTEMNLP05.tff）
  strongsubj ±1.5 / weaksubj ±1.0

另将 HowNet 程度级别词语（中文）按类目并入 zh_degree.csv（扩充程度词覆盖）。
产物：trilingual_sentiment/data/{zh,ja,en}_sentiment.csv

用法：python tools/build_full_lexicons.py
"""
from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DICT_DIR = ROOT / "dictionaries"
DATA_DIR = ROOT / "trilingual_sentiment" / "data"
SAMPLE_BACKUP = DICT_DIR / "sample_subset"

_PAREN_RE = re.compile(r"[(（][^)）]*[)）]")
_GROUP_HEADER_RE = re.compile(r"^\s*\d+[.．、]")


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"无法解码 {path}")


def _clean_word(w: str) -> str:
    return _PAREN_RE.sub("", w).strip()


def load_hownet_file(path: Path) -> list[str]:
    words: list[str] = []
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line or _GROUP_HEADER_RE.match(line):
            continue
        # 首行是「类目名 + 词数」表头（无实际词条或含数量），整行带数字表头跳过
        if re.match(r"^[^\s]+\s+\d+$", line):
            continue
        for w in re.split(r"[\s,，、;；/|]+", line):
            w = _clean_word(w)
            if w and not w.isdigit():
                words.append(w)
    return words


def build_zh() -> dict[str, float]:
    plan = {
        "正面情感词语（中文）.txt": 1.5,
        "负面情感词语（中文）.txt": -1.5,
        "正面评价词语（中文）.txt": 1.0,
        "负面评价词语（中文）.txt": -1.0,
    }
    lex: dict[str, float] = {}
    for fname, score in plan.items():
        words = load_hownet_file(DICT_DIR / "hownet" / fname)
        for w in words:
            # 冲突（同一词出现在多类）：保留绝对值更大者（情感类优先于评价类）
            if w not in lex or abs(score) > abs(lex[w]):
                lex[w] = score
        print(f"  {fname}: {len(words)} 词")
    return lex


def build_ja() -> dict[str, float]:
    raw: dict[str, set[str]] = {"p": set(), "n": set()}  # 极性 → 词集合
    # pn.csv：word \t p|n|e \t 注释
    for line in _read_text(DICT_DIR / "pn.csv.m3.120408.trim").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        word = _clean_word(parts[0].strip().strip('"'))
        pol = parts[1].strip().lower()
        if word and pol in ("p", "n"):
            raw[pol].add(word)
    # wago：ポジ（評価|経験）|ネガ（評価|経験） \t 词
    for line in _read_text(DICT_DIR / "wago.121808.pn").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        pol_tag = parts[0].strip()
        word = _clean_word(parts[1].strip())
        if not word:
            continue
        if pol_tag.startswith("ポジ"):
            raw["p"].add(word)
        elif pol_tag.startswith("ネガ"):
            raw["n"].add(word)
    # 双向冲突词（既 p 又 n）剔除
    conflict = raw["p"] & raw["n"]
    lex: dict[str, float] = {}
    for w in raw["p"] - conflict:
        lex[w] = 1.0
    for w in raw["n"] - conflict:
        lex[w] = -1.0
    print(f"  pn.csv: p={len(raw['p'])} n={len(raw['n'])}（含 wago 合并）；剔除双向冲突 {len(conflict)}")
    return lex


def build_en() -> dict[str, float]:
    lex: dict[str, float] = {}
    path = DICT_DIR / "subjclueslen1-HLTEMNLP05.tff"
    for line in _read_text(path).splitlines():
        fields = dict(
            kv.split("=", 1) for kv in line.split() if "=" in kv
        )
        word = _clean_word(fields.get("word1", ""))
        pol = fields.get("priorpolarity", "").lower()
        if not word or pol not in ("positive", "negative"):
            continue  # both / neutral 不收录
        mag = 1.5 if fields.get("type") == "strongsubj" else 1.0
        score = mag if pol == "positive" else -mag
        # 同词多词性：保留绝对值更大者
        if word not in lex or abs(score) > abs(lex[word]):
            lex[word] = score
    return lex


def merge_hownet_degree(path_out: Path) -> int:
    """HowNet 程度级别词语（中文）按类目权重并入 zh_degree.csv。"""
    cat_weight = [
        (re.compile(r"极其|最"), 2.0),
        (re.compile(r"超"), 1.8),
        (re.compile(r"很"), 1.5),
        (re.compile(r"较"), 1.2),
        (re.compile(r"稍稍|稍欠|不足"), 0.5),
    ]
    existing: dict[str, float] = {}
    for row in csv.reader(path_out.read_text(encoding="utf-8-sig").splitlines()):
        if row and row[0].strip() and not row[0].startswith("#") and row[0].lower() != "word":
            try:
                existing[row[0].strip()] = float(row[1])
            except (IndexError, ValueError):
                continue

    added = 0
    cur_weight = None
    for line in _read_text(DICT_DIR / "hownet" / "程度级别词语（中文）.txt").splitlines():
        line = line.strip()
        if not line:
            continue
        if _GROUP_HEADER_RE.match(line) or re.match(r"^[^\s]+\s+\d+$", line):
            for pat, w in cat_weight:
                if pat.search(line):
                    cur_weight = w
                    break
            continue
        if cur_weight is None:
            continue
        for w in re.split(r"[\s,，、;；/|]+", line):
            w = _clean_word(w)
            if w and w not in existing:
                existing[w] = cur_weight
                added += 1

    with path_out.open("w", encoding="utf-8") as f:
        f.write("# 中文程度副词表（格式: 词语,权重；权重>1 增强，<1 减弱）\n")
        f.write("# 来源：本项目自定词表 + 知网 HowNet 程度级别词语（按类目映射权重）\n")
        for w, v in sorted(existing.items(), key=lambda kv: (-kv[1], kv[0])):
            f.write(f"{w},{v:g}\n")
    return added


def write_csv(path: Path, lex: dict[str, float], header: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write(header)
        for w, v in sorted(lex.items(), key=lambda kv: kv[0]):
            f.write(f"{w},{v:g}\n")


def main() -> None:
    SAMPLE_BACKUP.mkdir(parents=True, exist_ok=True)
    for f in DATA_DIR.glob("*_sentiment.csv"):
        shutil.copy2(f, SAMPLE_BACKUP / f.name)

    print("构建中文词典（HowNet）...")
    zh = build_zh()
    print("构建日语词典（単語感情極性対応表 + wago）...")
    ja = build_ja()
    print("构建英语词典（MPQA）...")
    en = build_en()

    write_csv(
        DATA_DIR / "zh_sentiment.csv", zh,
        "# 中文情感词典：知网 HowNet「情感分析用词语集(beta 版)」\n"
        "# 分值约定：正面情感 +1.5 / 负面情感 -1.5 / 正面评价 +1.0 / 负面评价 -1.0\n"
        "# 原始文件：dictionaries/hownet/（构建脚本 tools/build_full_lexicons.py）\n",
    )
    write_csv(
        DATA_DIR / "ja_sentiment.csv", ja,
        "# 日本語感情極性辞書：単語感情極性対応表（日本語評価極性辞書）\n"
        "# pn.csv.m3.120408.trim（名詞）+ wago.121808.pn（用言），p→+1.0 / n→-1.0，双向冲突词剔除\n"
        "# 原始文件：dictionaries/（東北大学 乾・岡﨑研究室 Open Resources）\n",
    )
    write_csv(
        DATA_DIR / "en_sentiment.csv", en,
        "# English sentiment lexicon: MPQA Subjectivity Lexicon\n"
        "# (Wilson, Wiebe & Hoffmann, HLT/EMNLP 2005; subjclueslen1-HLTEMNLP05.tff)\n"
        "# Conventions: strongsubj ±1.5 / weaksubj ±1.0; both/neutral excluded\n"
        "# Raw file: dictionaries/subjclueslen1-HLTEMNLP05.tff\n",
    )

    added_deg = merge_hownet_degree(DATA_DIR / "zh_degree.csv")

    print()
    print(f"zh_sentiment.csv: {len(zh)} 词条")
    print(f"ja_sentiment.csv: {len(ja)} 词条")
    print(f"en_sentiment.csv: {len(en)} 词条")
    print(f"zh_degree.csv 新增 HowNet 程度词: {added_deg}")
    print(f"精选子集已备份至 {SAMPLE_BACKUP}")


if __name__ == "__main__":
    main()
