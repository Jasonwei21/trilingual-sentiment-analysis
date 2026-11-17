"""情感词典：存储与多格式加载。

支持的扩展格式：
- CSV：word,score 两列（内置示例格式）
- JSON：{word: score}
- HowNet 情感分析用词语集目录（正面/负面情感词语.txt、正面/负面评价词语.txt）
- MPQA 词典（.lex，type=strongsubj ... priorpolarity=negative）
- 単語感情極性対応表（pn.csv，制表符分隔，极性列 p/n/e）

词典缺失时抛出 FileNotFoundError，格式错误抛出 LexiconError，
由上层（SentimentAnalyzer / CLI）决定降级策略（如返回「无法判断」）。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Iterable

__all__ = ["LexiconError", "SentimentLexicon"]

# 去掉词条里的括注：如「安全(计算机)」→「安全」
_PAREN_RE = re.compile(r"[(（][^)）]*[)）]")


class LexiconError(Exception):
    """词典内容格式错误。"""


class SentimentLexicon:
    """情感词典：词条 -> 基础分值（正=正面，负=负面）。"""

    def __init__(self, language: str = "", name: str = "") -> None:
        self.language = language
        self.name = name
        self._scores: dict[str, float] = {}

    # ---------- 基础操作 ----------
    def add(self, word: str, score: float) -> None:
        word = word.strip()
        if not word:
            raise LexiconError("词条不能为空")
        self._scores[word] = float(score)

    def get(self, word: str) -> float | None:
        return self._scores.get(word)

    def __getitem__(self, word: str) -> float:
        try:
            return self._scores[word]
        except KeyError:
            raise KeyError(f"词条不在词典中: {word!r}") from None

    def words(self) -> list[str]:
        return list(self._scores)

    def items(self) -> list[tuple[str, float]]:
        return list(self._scores.items())

    def copy(self) -> "SentimentLexicon":
        clone = SentimentLexicon(self.language, self.name)
        clone._scores = dict(self._scores)
        return clone

    def __contains__(self, word: str) -> bool:
        return word in self._scores

    def __len__(self) -> int:
        return len(self._scores)

    def __iter__(self):
        return iter(self._scores)

    def __repr__(self) -> str:
        return f"<SentimentLexicon {self.name or self.language!r} n={len(self)}>"

    # ---------- CSV / JSON ----------
    @classmethod
    def from_csv(cls, path: str | Path, language: str = "", name: str = "") -> "SentimentLexicon":
        lex = cls(language, name or Path(path).stem)
        lex.load_csv(path)
        return lex

    def load_csv(self, path: str | Path) -> None:
        p = Path(path)
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            for lineno, row in enumerate(csv.reader(f), 1):
                if not row:
                    continue
                cells = [c.strip() for c in row]
                first = cells[0]
                if not first or first.startswith("#"):
                    continue
                if first.lower() in ("word", "词语", "語", "単語"):
                    continue  # 表头
                if len(cells) < 2:
                    raise LexiconError(f"{p}:{lineno} 需要两列 word,score，实际: {row!r}")
                try:
                    score = float(cells[1])
                except ValueError as e:
                    raise LexiconError(f"{p}:{lineno} 分值无效: {cells[1]!r}") from e
                self.add(first, score)

    @classmethod
    def from_json(cls, path: str | Path, language: str = "", name: str = "") -> "SentimentLexicon":
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise LexiconError(f"{p} 应为 {{word: score}} 对象")
        lex = cls(language, name or p.stem)
        for word, score in data.items():
            try:
                lex.add(str(word), float(score))
            except (TypeError, ValueError) as e:
                raise LexiconError(f"{p} 条目 {word!r} 分值无效: {score!r}") from e
        return lex

    # ---------- HowNet 情感分析用词语集 ----------
    @classmethod
    def from_hownet_dir(
        cls,
        directory: str | Path,
        language: str = "zh",
        name: str = "HowNet",
    ) -> "SentimentLexicon":
        """读取 HowNet 情感词语集目录。

        识别文件（可带 .txt 扩展名）：
        正面情感词语 / 负面情感词语 / 正面评价词语 / 负面评价词语
        情感类按 ±1.5 计，评价类按 ±1.0 计。
        """
        d = Path(directory)
        if not d.is_dir():
            raise FileNotFoundError(f"HowNet 词典目录不存在: {d}")
        plan = {
            "正面情感词语": 1.5,
            "负面情感词语": -1.5,
            "正面评价词语": 1.0,
            "负面评价词语": -1.0,
        }
        lex = cls(language, name)
        loaded_any = False
        for stem, score in plan.items():
            fp = d / f"{stem}.txt"
            if not fp.exists():
                fp = d / stem
            if not fp.exists():
                continue
            loaded_any = True
            with fp.open("r", encoding="utf-8-sig") as f:
                for line in f:
                    line = _PAREN_RE.sub("", line).strip()
                    if not line or line.startswith("#"):
                        continue
                    for word in re.split(r"[\s,，、;；]+", line):
                        if word:
                            lex.add(word, score)
        if not loaded_any:
            raise LexiconError(f"{d} 下未找到 HowNet 情感词语集文件")
        return lex

    # ---------- MPQA ----------
    @classmethod
    def from_mpqa(
        cls,
        path: str | Path,
        language: str = "en",
        name: str = "MPQA",
        strong_score: float = 1.5,
        weak_score: float = 1.0,
    ) -> "SentimentLexicon":
        """解析 MPQA 词典（subjectivity clues .lex）。

        每行形如: type=strongsubj len=1 word1=abandon pos1=verb priorpolarity=negative
        strongsubj/weaksubj 决定强度，priorpolarity 决定正负；both/neutral 跳过。
        """
        p = Path(path)
        lex = cls(language, name)
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fields: dict[str, str] = {}
                for part in line.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        fields[k.strip()] = v.strip()
                polarity = fields.get("priorpolarity", "").lower()
                if polarity in ("positive", "positive?"):
                    sign = 1.0
                elif polarity in ("negative", "negative?"):
                    sign = -1.0
                else:
                    continue  # both / neutral / 未知
                magnitude = strong_score if fields.get("type") == "strongsubj" else weak_score
                word_parts = [
                    fields[k]
                    for k in sorted(fields)
                    if re.fullmatch(r"word\d+", k)
                ]
                if not word_parts:
                    continue
                lex.add(" ".join(word_parts), sign * magnitude)
        return lex

    # ---------- 単語感情極性対応表 ----------
    @classmethod
    def from_jp_table(
        cls,
        path: str | Path,
        language: str = "ja",
        name: str = "単語感情極性対応表",
        pos_score: float = 1.0,
        neg_score: float = -1.0,
    ) -> "SentimentLexicon":
        """解析「単語感情極性対応表」(pn.csv 等)。

        兼容两种列排布：
        - 単語 / 読み / 品詞 / 極性(p·n·e)（完整版）
        - 単語 / 極性 / 注释（pn.csv.m3.120408.trim）
        p(ポジティブ)→+pos_score，n(ネガティブ)→-neg_score，e(中立)跳过。
        """
        p = Path(path)
        lex = cls(language, name)
        pol_values = {"p", "n", "e", "ポジティブ", "ネガティブ", "中庸", "positive", "negative", "neutral", "pos", "neg"}
        with p.open("r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip() or line.lstrip().startswith(("#", ";")):
                    continue
                parts = line.split("\t") if "\t" in line else line.split(",")
                if len(parts) < 2:
                    continue
                word = _PAREN_RE.sub("", parts[0]).strip().strip('"')
                if not word:
                    continue
                # 极性取第一个形如 p/n/e 的字段（不固定列位）
                polarity = ""
                for cell in parts[1:]:
                    c = cell.strip().lower()
                    if c in pol_values:
                        polarity = c
                        break
                if polarity in ("p", "ポジティブ", "positive", "pos") or polarity.startswith("ポジ"):
                    lex.add(word, pos_score)
                elif polarity in ("n", "ネガティブ", "negative", "neg") or polarity.startswith("ネガ"):
                    lex.add(word, neg_score)
                # e / 中立 / 中庸 → 中性词，不进情感词典
        return lex
