"""三语（zh/ja/en）情感极性判定核心。

判定流程：
1. 校验输入与语言代码 → 无效代码返回「无法判断」
2. 按语言分词（ja 取词元 lemma）
3. 词典命中：直接命中，或经词缀拆分命中
   - 中文前缀否定：不好 → 不 + 好
   - 日语后缀否定：良くない → 良い + ない；连用形还原：良く → 良い
   - 英语后缀否定：n't（分词阶段已展开为 not，窗口规则兜底）
4. 规则加权：weighted = base × (-1)^否定 × 程度权重
5. 汇总：score = Σ weighted，标签按分值符号 / 无命中判定

扩展点：
- add_word() / set_lexicon() / load_lexicon() 扩展词典（csv/json/hownet/mpqa/jp）
- register_language() 注册新语言的 LanguageProfile（分词+词典+规则）
- 规则窗口、程度上限均可在构造函数配置
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .lexicon import LexiconError, SentimentLexicon
from .models import (
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    LABEL_UNKNOWN,
    MatchedWord,
    SentimentResult,
)
from .rules import DegreeRule, NegationRule, RuleEngine, load_degree_weights, load_negation_words
from .tokenizers import build_tokenizer

__all__ = ["LanguageProfile", "SentimentAnalyzer", "DEFAULT_DATA_DIR"]

def _default_data_dir() -> Path:
    """词典数据目录：开发态为包内 data/，PyInstaller 打包态为 _MEIPASS 下的同名目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "trilingual_sentiment" / "data"
    return Path(__file__).resolve().parent / "data"


DEFAULT_DATA_DIR = _default_data_dir()

_EPS = 1e-9

# 各语言的内置数据文件与词缀拆分配置
_LANGUAGE_DEFAULTS: dict[str, dict] = {
    "zh": {
        "name": "中文",
        "sentiment_file": "zh_sentiment.csv",
        "degree_file": "zh_degree.csv",
        "negation_file": "zh_negation.txt",
        # 好 / いい … 前缀否定：不好 / 没好 → 词干回查
        "negation_prefixes": ("不", "没", "无", "未", "非", "别", "莫", "勿"),
        "negation_suffixes": (),
        # 否定词窗口方向：中文否定语在前
        "negation_direction": "left",
    },
    "ja": {
        "name": "日本語",
        "sentiment_file": "ja_sentiment.csv",
        "degree_file": "ja_degree.csv",
        "negation_file": "ja_negation.txt",
        "negation_prefixes": (),
        # 良くない / しなかった … → 后缀否定 + 词干（长后缀优先）
        "negation_suffixes": ("なかった", "ません", "ない", "なかっ", "ず", "ぬ"),
        # 日语否定词在情感词之后（…ない），窗口向右看
        "negation_direction": "right",
    },
    "en": {
        "name": "English",
        "sentiment_file": "en_sentiment.csv",
        "degree_file": "en_degree.csv",
        "negation_file": "en_negation.txt",
        "negation_prefixes": (),
        "negation_suffixes": ("n't",),
        "negation_direction": "left",
    },
}


@dataclass
class LanguageProfile:
    """一种语言的完整判定配置。

    Attributes:
        code: 语言代码（小写，如 zh）。
        name: 展示名。
        lexicon: 情感词典。
        negation_rule: 否定反转规则。
        degree_rule: 程度加权规则。
        tokenizer: 分词函数 text -> tokens。
        negation_prefixes: 参与词缀拆分的否定前缀（中文）。
        negation_suffixes: 参与词缀拆分的否定后缀（日语/英语）。
    """

    code: str
    name: str
    lexicon: SentimentLexicon
    negation_rule: NegationRule
    degree_rule: DegreeRule
    tokenizer: Callable[[str], list[str]]
    negation_prefixes: tuple[str, ...] = ()
    negation_suffixes: tuple[str, ...] = ()


def _expand_stem(lang: str, stem: str) -> list[str]:
    """词干还原候选：日语连用形「〜く」→ 基本形「〜い」。"""
    out = [stem]
    if lang == "ja" and stem.endswith("く") and len(stem) >= 2:
        out.append(stem[:-1] + "い")
    return out


class SentimentAnalyzer:
    """三语情感极性判定器。"""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        *,
        negation_window: int = 2,
        degree_window: int = 2,
        max_degree_weight: float = 3.0,
    ) -> None:
        self._data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._negation_window = negation_window
        self._degree_window = degree_window
        self._max_degree_weight = max_degree_weight
        self._profiles: dict[str, LanguageProfile] = {}
        self._vocab: dict[str, set[str]] = {}
        self._load_warnings: dict[str, list[str]] = {}
        for code in _LANGUAGE_DEFAULTS:
            self._load_builtin(code)

    # ---------------- 内置装载 ----------------
    def _load_builtin(self, code: str) -> None:
        cfg = _LANGUAGE_DEFAULTS[code]
        warnings: list[str] = []

        lex_path = self._data_dir / cfg["sentiment_file"]
        try:
            lexicon = SentimentLexicon.from_csv(lex_path, language=code, name=cfg["name"])
        except FileNotFoundError:
            lexicon = SentimentLexicon(language=code, name=cfg["name"])
            warnings.append(f"情感词典文件缺失: {lex_path}")
        except LexiconError as e:
            lexicon = SentimentLexicon(language=code, name=cfg["name"])
            warnings.append(f"情感词典加载失败: {e}")

        neg_path = self._data_dir / cfg["negation_file"]
        try:
            negation_words = load_negation_words(neg_path)
        except FileNotFoundError:
            negation_words = set()
            warnings.append(f"否定词表缺失: {neg_path}")

        deg_path = self._data_dir / cfg["degree_file"]
        try:
            degree_weights = load_degree_weights(deg_path)
        except FileNotFoundError:
            degree_weights = {}
            warnings.append(f"程度词表缺失: {deg_path}")
        except ValueError as e:
            degree_weights = {}
            warnings.append(f"程度词表加载失败: {e}")

        vocab = set(lexicon.words()) | negation_words | set(degree_weights)
        tokenizer, tok_warning = build_tokenizer(code, vocab)
        if tok_warning:
            warnings.append(tok_warning)

        profile = LanguageProfile(
            code=code,
            name=cfg["name"],
            lexicon=lexicon,
            negation_rule=NegationRule(
                negation_words,
                window=self._negation_window,
                direction=cfg.get("negation_direction", "left"),
            ),
            degree_rule=DegreeRule(
                degree_weights, window=self._degree_window, max_weight=self._max_degree_weight
            ),
            tokenizer=tokenizer,
            negation_prefixes=tuple(sorted(cfg["negation_prefixes"], key=len, reverse=True)),
            negation_suffixes=tuple(sorted(cfg["negation_suffixes"], key=len, reverse=True)),
        )
        self._profiles[code] = profile
        self._vocab[code] = vocab
        self._load_warnings[code] = warnings

    def _get_profile(self, lang: str) -> LanguageProfile:
        code = (lang or "").strip().lower()
        if code not in self._profiles:
            raise ValueError(f"未知语言代码: {lang!r}，支持: {', '.join(sorted(self._profiles))}")
        return self._profiles[code]

    def _rebuild_vocab(self, code: str) -> None:
        profile = self._profiles[code]
        vocab = set(profile.lexicon.words()) | profile.negation_rule.words | set(profile.degree_rule.weights)
        self._vocab[code] = vocab

    # ---------------- 扩展 API ----------------
    def supported_languages(self) -> list[str]:
        return sorted(self._profiles)

    def register_language(self, profile: LanguageProfile) -> None:
        """注册/替换一种语言配置（新语言扩展的总入口）。"""
        self._profiles[profile.code] = profile
        self._rebuild_vocab(profile.code)
        self._load_warnings.setdefault(profile.code, [])

    def add_word(self, lang: str, word: str, score: float) -> None:
        """向词典动态追加一个词条。"""
        profile = self._get_profile(lang)
        profile.lexicon.add(word, score)
        self._vocab[profile.code].add(word.strip())

    def set_lexicon(self, lang: str, lexicon: SentimentLexicon) -> None:
        """整体替换某种语言的词典。"""
        profile = self._get_profile(lang)
        profile.lexicon = lexicon
        self._rebuild_vocab(profile.code)

    def load_lexicon(self, lang: str, path: str | Path, fmt: str = "csv") -> None:
        """从文件载入词典并替换当前词典。

        fmt: csv | json | hownet | mpqa | jp
        """
        code = self._get_profile(lang).code
        loaders = {
            "csv": lambda p: SentimentLexicon.from_csv(p, language=code),
            "json": lambda p: SentimentLexicon.from_json(p, language=code),
            "hownet": lambda p: SentimentLexicon.from_hownet_dir(p, language=code),
            "mpqa": lambda p: SentimentLexicon.from_mpqa(p, language=code),
            "jp": lambda p: SentimentLexicon.from_jp_table(p, language=code),
        }
        if fmt not in loaders:
            raise ValueError(f"未知词典格式: {fmt!r}，可选: {', '.join(sorted(loaders))}")
        self.set_lexicon(lang, loaders[fmt](path))

    # ---------------- 判定 ----------------
    def _degree_split(self, profile: LanguageProfile, token: str) -> tuple[str, str, float] | None:
        """程度前缀 + 词干拆分：太慢 → (慢, 太, 1.8)。返回 (词条, 程度词, 权重)。"""
        for deg, weight in sorted(profile.degree_rule.weights.items(), key=lambda kv: -len(kv[0])):
            if token.startswith(deg) and len(token) > len(deg):
                stem = token[len(deg) :]
                for cand in _expand_stem(profile.code, stem):
                    if cand in profile.lexicon:
                        return cand, deg, float(weight)
        return None

    def _lookup_token(
        self, profile: LanguageProfile, token: str
    ) -> tuple[str, bool, str | None, str | None, float] | None:
        """词典命中：返回 (词条, 是否词缀否定, 否定词缀, 程度词, 程度权重)。"""
        key = token.casefold() if profile.code == "en" else token
        lex = profile.lexicon

        def try_stem(stem: str) -> str | None:
            for cand in _expand_stem(profile.code, stem):
                if cand in lex:
                    return cand
            return None

        if key in lex:
            return key, False, None, None, 1.0
        # 规则词（否定词/程度词）本身不参与构词拆分，防止「非常→常」这类误拆
        if key in profile.negation_rule.words or key in profile.degree_rule.weights:
            return None
        # 后缀否定：…ない / …n't → 词干回查
        for suf in profile.negation_suffixes:
            if key.endswith(suf) and len(key) > len(suf):
                stem = key[: -len(suf)]
                hit = try_stem(stem)
                if hit:
                    return hit, True, suf, None, 1.0
        # 前缀否定：不好 / 没好 → 词干回查
        # （否定前缀内再嵌程度词：不太好 → 不+太+好；此类「不太X」是弱化否定，
        #   不套用程度放大权重，只做极性反转）
        for pre in profile.negation_prefixes:
            if key.startswith(pre) and len(key) > len(pre):
                stem = key[len(pre) :]
                hit = try_stem(stem)
                if hit:
                    return hit, True, pre, None, 1.0
                deg_hit = self._degree_split(profile, stem)
                if deg_hit:
                    hit2, _deg, _weight = deg_hit
                    return hit2, True, pre, None, 1.0
        # 程度前缀（无否定）：太慢 → 太+慢
        deg_hit = self._degree_split(profile, key)
        if deg_hit:
            hit2, deg, weight = deg_hit
            return hit2, False, None, deg, weight
        # 词形还原（无否定）：日语连用形 良く → 良い
        for cand in _expand_stem(profile.code, key):
            if cand != key and cand in lex:
                return cand, False, None, None, 1.0
        return None

    def analyze(self, text: str, lang: str) -> SentimentResult:
        """判定一句话/词的情感极性。

        Raises:
            ValueError: 输入为空（含纯空白）。
        """
        if text is None or not str(text).strip():
            raise ValueError("输入文本不能为空")

        raw_code = "" if lang is None else str(lang).strip()
        code = raw_code.lower()
        warnings = list(self._load_warnings.get(code, []))

        if code not in self._profiles:
            return SentimentResult(
                text=str(text),
                language=raw_code or "(空)",
                score=0.0,
                label=LABEL_UNKNOWN,
                matched=[],
                warnings=warnings
                + [f"未知语言代码: {raw_code!r}，支持: {', '.join(sorted(self._profiles))}"],
            )

        profile = self._profiles[code]
        if len(profile.lexicon) == 0:
            return SentimentResult(
                text=str(text),
                language=code,
                score=0.0,
                label=LABEL_UNKNOWN,
                matched=[],
                warnings=warnings + ["情感词典缺失或为空，无法判定"],
            )

        engine = RuleEngine(profile.negation_rule, profile.degree_rule)
        tokens = profile.tokenizer(str(text))
        matched: list[MatchedWord] = []

        for i, tok in enumerate(tokens):
            hit = self._lookup_token(profile, tok)
            if hit is None:
                continue
            lex_key, morph_neg, morph_trigger, morph_degree, morph_weight = hit
            rule_hit = engine.apply(tokens, i)
            # 词缀否定与窗口否定按异或合成（双重否定复原）
            negated = morph_neg != rule_hit.negated
            # 程度：词缀内嵌（太慢）与窗口（非常 好）可叠加，封顶防溢出
            degree_weight = morph_weight * rule_hit.degree_weight
            if degree_weight > profile.degree_rule.max_weight:
                degree_weight = profile.degree_rule.max_weight
            degree = morph_degree or rule_hit.degree
            base = profile.lexicon[lex_key]
            sign = -1.0 if negated else 1.0
            weighted = base * sign * degree_weight
            trigger = morph_trigger or (rule_hit.negation_trigger if negated else None)
            matched.append(
                MatchedWord(
                    word=lex_key,
                    base_score=base,
                    weighted_score=weighted,
                    surface=tok,
                    negated=negated,
                    negation_trigger=trigger,
                    degree=degree,
                    degree_weight=degree_weight,
                    position=i,
                )
            )

        score = sum(m.weighted_score for m in matched)
        if not matched:
            label = LABEL_UNKNOWN
        elif score > _EPS:
            label = LABEL_POSITIVE
        elif score < -_EPS:
            label = LABEL_NEGATIVE
        else:
            label = LABEL_NEUTRAL

        return SentimentResult(
            text=str(text),
            language=code,
            score=score,
            label=label,
            matched=matched,
            warnings=warnings,
        )

    # ---------------- GUI / 调试辅助 ----------------
    def tokenize(self, text: str, lang: str) -> list[str]:
        """按语言分词（供外部展示分词结果）。"""
        profile = self._get_profile(lang)
        return profile.tokenizer(str(text))

    def explain(self, text: str, lang: str) -> dict:
        """一次调用返回「分词标注 + 判定结果」，方便 GUI 消费。

        tokens 中每项: {text, kind, word}
        kind ∈ plain | sentiment | negation | degree
        （sentiment 项带 word=命中的词条；否定/程度词标注规则触发词）
        """
        result = self.analyze(text, lang)
        profile = self._profiles[result.language]
        tokens = profile.tokenizer(str(text))

        matched_by_pos = {m.position: m for m in result.matched}
        degree_words = set(profile.degree_rule.weights)
        tagged: list[dict] = []
        for i, tok in enumerate(tokens):
            item: dict = {"text": tok, "kind": "plain"}
            m = matched_by_pos.get(i)
            if m is not None:
                item["kind"] = "sentiment"
                item["word"] = m.word
                item["weighted_score"] = m.weighted_score
            elif tok in profile.negation_rule.words:
                item["kind"] = "negation"
            elif tok in degree_words:
                item["kind"] = "degree"
            tagged.append(item)

        return {"tokens": tagged, **result.to_dict()}
