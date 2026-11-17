"""数据模型：匹配词与判定结果。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


# 极性标签常量
LABEL_POSITIVE = "正面"
LABEL_NEGATIVE = "负面"
LABEL_NEUTRAL = "中性"
LABEL_UNKNOWN = "无法判断"


@dataclass
class MatchedWord:
    """匹配到的一个情感词及其加权信息。

    Attributes:
        word: 命中词典的词条（如「好」）。
        surface: 文本中的词面（如「不好」）。
        base_score: 词典中的基础分值。
        weighted_score: 经否定反转与程度加权后的最终分值。
        negated: 是否被否定规则反转。
        negation_trigger: 触发否定的词/词缀（如「不」「ない」「n't」）。
        degree: 触发加权的程度词（如「非常」「very」），无则为 None。
        degree_weight: 程度权重（乘数，默认 1.0）。
        position: 在分词序列中的下标。
    """

    word: str
    base_score: float
    weighted_score: float
    surface: str = ""
    negated: bool = False
    negation_trigger: str | None = None
    degree: str | None = None
    degree_weight: float = 1.0
    position: int = -1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SentimentResult:
    """一次判定的完整输出。

    Attributes:
        text: 原始输入文本。
        language: 语言代码（zh/ja/en；未知代码原样保留以便排查）。
        score: 整体极性分值（各匹配词加权分之和）。
        label: 极性标签——正面/负面/中性/无法判断。
        matched: 匹配到的情感词列表（含基础分值与加权后分值）。
        warnings: 处理过程中的警告（词典缺失、分词降级等）。
    """

    text: str
    language: str
    score: float
    label: str
    matched: list[MatchedWord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_determinate(self) -> bool:
        """是否为可判定结果（非「无法判断」）。"""
        return self.label != LABEL_UNKNOWN

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "score": self.score,
            "label": self.label,
            "matched": [m.to_dict() for m in self.matched],
            "warnings": list(self.warnings),
        }
