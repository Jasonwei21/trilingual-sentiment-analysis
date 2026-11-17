"""分词器：按语言选择 jieba / fugashi / 空格分词，缺依赖时用词典最长匹配兜底。

- zh: jieba.lcut；未安装 jieba → 基于词表的最长匹配（词表=词典∪规则词）
- ja: fugashi + UniDic 词元(lemma)；未安装 → 词表最长匹配 + い形容词连用形还原（良く→良い）
- en: 空格/正则分词 + 缩写展开（isn't → is not）

所有分词器返回 token 列表；日语优先返回词元，便于词典命中。
兜底实现只为「可运行」，生产建议安装对应分词库。
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Iterable

__all__ = ["TokenizerUnavailable", "build_tokenizer", "en_tokenize", "greedy_tokenize"]


class TokenizerUnavailable(RuntimeError):
    """请求的分词库不可用（未安装或加载失败）。"""


# 一个连续的 CJK/假名/长音段，或一段拉丁词（可含撇号：isn't）
_RUN_RE = re.compile(r"[぀-ヿ一-鿿ー]+|[A-Za-z]+(?:'[A-Za-z]+)?")
_EN_WORD_RE = re.compile(r"[a-z]+")
_MAX_VOCAB_MATCH = 8

# ja 词形候选：连用形「〜く」→ 基本形「〜い」（良く→良い、美しく→美しい）
def _ja_variants(cand: str) -> list[str]:
    out = [cand]
    if cand.endswith("く") and len(cand) >= 2:
        out.append(cand[:-1] + "い")
    return out


def _plain_variants(cand: str) -> list[str]:
    return [cand]


def greedy_tokenize(
    text: str,
    vocab: Iterable[str],
    transform: Callable[[str], list[str]] | None = None,
) -> list[str]:
    """词表最长匹配兜底分词（CJK 段逐字前进，拉丁段整词小写）。"""
    vocab_set = set(vocab)
    if transform is None:
        transform = _plain_variants
    tokens: list[str] = []
    for m in _RUN_RE.finditer(text):
        run = m.group(0)
        if run[0].isascii():
            tokens.append(run.lower())
            continue
        i, n = 0, len(run)
        while i < n:
            matched_key: str | None = None
            matched_len = 0
            for j in range(min(n, i + _MAX_VOCAB_MATCH), i, -1):
                for variant in transform(run[i:j]):
                    if variant in vocab_set:
                        matched_key, matched_len = variant, j - i
                        break
                if matched_key is not None:
                    break
            if matched_key is not None:
                tokens.append(matched_key)
                i += matched_len
            else:
                tokens.append(run[i])
                i += 1
    return tokens


# ---------------- 实际分词实现 ----------------

def _jieba_cut(text: str) -> list[str]:
    try:
        import jieba
    except ImportError as e:  # pragma: no cover - 由 build_tokenizer 提前拦截
        raise TokenizerUnavailable("jieba 未安装") from e
    logging.getLogger("jieba").setLevel(logging.WARNING)
    if not getattr(jieba, "_wb_cache_fixed", False):
        # 打包/只读环境下词典缓存写到系统临时目录，避免写程序目录失败
        import os
        import tempfile

        try:
            jieba.dt.cache_file = os.path.join(tempfile.gettempdir(), "jieba_wb_dict.cache")
        except Exception:
            pass
        jieba._wb_cache_fixed = True
    return [w for w in jieba.lcut(text) if w.strip()]


_fugashi_tagger = None


def _get_fugashi():
    global _fugashi_tagger
    if _fugashi_tagger is None:
        from fugashi import Tagger

        _fugashi_tagger = Tagger()
    return _fugashi_tagger


def _fugashi_tokens(text: str, vocab: set[str]) -> list[str]:
    """fugashi 分词：优先输出能在词表命中的形式（词元/词面）。

    UniDic 词元常与常用写法不同（ない→無い、とても→迚も），
    因此按「词面 → 词元」取第一个命中词表者；都不命中时退回词元。
    这样词典与规则表可以用常用写法，且输出展示更自然。
    """
    tagger = _get_fugashi()
    out: list[str] = []
    for word in tagger(text):
        feat = getattr(word, "feature", None)
        lemma = getattr(feat, "lemma", None) if feat is not None else None
        if not lemma:
            lemma = getattr(word, "dictionary_form", None) or getattr(word, "normalized_form", None)
        surface = word.surface or ""
        lemma = (lemma or "").strip()
        chosen = None
        for cand in (surface, lemma):
            if cand and cand in vocab:
                chosen = cand
                break
        out.append(chosen or lemma or surface)
    return [t for t in out if t]


def en_tokenize(text: str) -> list[str]:
    """英语：小写 + 缩写展开（n't → not）+ 字母词切分。"""
    t = text.lower()
    t = t.replace("cannot", "can not").replace("n't", " not")
    return _EN_WORD_RE.findall(t)


def build_tokenizer(
    lang: str,
    vocab: Iterable[str] | None = None,
) -> tuple[Callable[[str], list[str]], str | None]:
    """按语言返回 (分词函数, 降级警告)。

    库不可用时自动降级为词表最长匹配，并在警告中说明。
    vocab 建议传入「词典∪规则词」的活集合，便于动态加词后仍可命中。
    """
    vocab_set = vocab if vocab is not None else set()
    if lang == "zh":
        try:
            import jieba  # noqa: F401
        except ImportError:
            return (
                lambda t: greedy_tokenize(t, vocab_set, _plain_variants),
                "jieba 未安装，中文分词已降级为词表最长匹配",
            )
        return _jieba_cut, None
    if lang == "ja":
        try:
            _get_fugashi()
        except Exception:
            return (
                lambda t: greedy_tokenize(t, vocab_set, _ja_variants),
                "fugashi/UniDic 未安装，日语分词已降级为词表最长匹配",
            )
        return lambda t: _fugashi_tokens(t, vocab_set), None
    if lang == "en":
        return en_tokenize, None
    raise ValueError(f"不支持的语言: {lang!r}")
