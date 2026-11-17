"""语言自动检测：基于字符集统计识别 zh / ja / en。

思路（无外部依赖、可解释）：
- 假名（平假名/片假名）只出现在日语 → 出现即判定 ja
- 否则有汉字 → zh
- 否则有拉丁字母 → en
- 置信度 = 判定脚本字符占「字母类字符」的比例（假名+汉字对日语都算日文书写）

混排文本（如「iPhone很好用」）按主导脚本判为 zh，置信度如实反映混排程度。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["LanguageGuess", "detect_language", "LANG_NAMES"]

# 汉字：CJK 统一表意(4E00-9FFF) + 扩展A(3400-4DBF) + 兼容表意(F900-FAFF)
_HAN_RE = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uF900-\uFAFF]")
# 假名：平假名/片假名/长音等(3040-30FF)
_KANA_RE = re.compile("[\u3040-\u30FF]")
_LATIN_RE = re.compile("[A-Za-z]")

LANG_ZH = "zh"
LANG_JA = "ja"
LANG_EN = "en"
LANG_UNKNOWN = "unknown"

LANG_NAMES = {LANG_ZH: "中文", LANG_JA: "日本語", LANG_EN: "English", LANG_UNKNOWN: "未知"}


@dataclass
class LanguageGuess:
    """语言识别结果。

    Attributes:
        code: zh / ja / en / unknown。
        confidence: 0~1，判定脚本字符占比。
        counts: 字符分布 {"han": 汉字, "kana": 假名, "latin": 拉丁字母}。
    """

    code: str
    confidence: float
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return LANG_NAMES.get(self.code, self.code)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "confidence": round(self.confidence, 3),
            "counts": dict(self.counts),
        }


def detect_language(text: str) -> LanguageGuess:
    """自动识别文本语言（zh/ja/en），无法识别返回 unknown。"""
    text = text or ""
    han = len(_HAN_RE.findall(text))
    kana = len(_KANA_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    counts = {"han": han, "kana": kana, "latin": latin}
    total = han + kana + latin
    if total == 0:
        return LanguageGuess(LANG_UNKNOWN, 0.0, counts)

    if kana > 0:
        # 假名是日语的决定性信号；汉字/假名都属于日文书写
        code = LANG_JA
        share = (kana + han) / total
    elif han > 0:
        code = LANG_ZH
        share = han / total
    else:
        code = LANG_EN
        share = latin / total

    return LanguageGuess(code, min(1.0, max(0.0, share)), counts)
