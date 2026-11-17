"""规则引擎：否定词反转与程度副词加权。

规则与语言解耦——只依赖「当前语言的否定词集合 / 程度词权重表」，
新语言只需提供两份小词表即可复用全部规则；新增规则（如转折词）
可实现自己的 scan() 并在 RuleEngine 中组合。
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

__all__ = [
    "RuleHit",
    "NegationRule",
    "DegreeRule",
    "RuleEngine",
    "load_negation_words",
    "load_degree_weights",
]

_SPLIT_RE = re.compile(r"[\s,，、;；/|]+")


def load_negation_words(path: str | Path) -> set[str]:
    """读取否定词表：每行一个词，支持 # 注释、空格/逗号/顿号分隔多个词。"""
    words: set[str] = set()
    with Path(path).open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            for w in _SPLIT_RE.split(line):
                if w:
                    words.add(w)
    return words


def load_degree_weights(path: str | Path) -> dict[str, float]:
    """读取程度词表：CSV 两列 word,weight。"""
    weights: dict[str, float] = {}
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        for lineno, row in enumerate(csv.reader(f), 1):
            if not row:
                continue
            cells = [c.strip() for c in row]
            if not cells[0] or cells[0].startswith("#"):
                continue
            if cells[0].lower() in ("word", "词语", "語", "単語"):
                continue
            if len(cells) < 2:
                raise ValueError(f"{p}:{lineno} 需要两列 word,weight，实际: {row!r}")
            try:
                weights[cells[0]] = float(cells[1])
            except ValueError as e:
                raise ValueError(f"{p}:{lineno} 权重无效: {cells[1]!r}") from e
    return weights


@dataclass(frozen=True)
class RuleHit:
    """规则合成结果。"""

    negated: bool
    negation_trigger: str | None
    degree: str | None
    degree_weight: float


class NegationRule:
    """否定词反转：窗口内奇数个否定词 → 极性取反，偶数个 → 双重否定复原。

    direction 控制窗口方向：
    - left：修饰语在前（中文「不 好」、英语「not good」）
    - right：否定在后（日语「良く ない」，否定词是后缀）
    - both：双向（可配置，误触发风险略高）
    """

    def __init__(self, words: Iterable[str], window: int = 2, direction: str = "left") -> None:
        self.words: frozenset[str] = frozenset(w for w in (x.strip() for x in words) if w)
        self.window = max(1, int(window))
        if direction not in ("left", "right", "both"):
            raise ValueError(f"direction 必须是 left/right/both，实际: {direction!r}")
        self.direction = direction

    def _positions(self, tokens: list[str], index: int) -> list[int]:
        pos: list[int] = []
        if self.direction in ("left", "both"):
            pos.extend(range(max(0, index - self.window), index))
        if self.direction in ("right", "both"):
            pos.extend(range(index + 1, min(len(tokens), index + 1 + self.window)))
        return pos

    def scan(self, tokens: list[str], index: int) -> tuple[bool, str | None]:
        """返回 (是否反转, 触发否定的词)。"""
        trigger: str | None = None
        count = 0
        for j in self._positions(tokens, index):
            tok = tokens[j]
            if tok in self.words:
                count += 1
                trigger = tok
        negated = count % 2 == 1
        return negated, (trigger if negated else None)


class DegreeRule:
    """程度副词加权：窗口内程度词权重连乘（设上限防溢出）。

    例：非常好 → ×2.0；not very good → ×1.5 后再反转。
    """

    def __init__(self, weights: Mapping[str, float], window: int = 2, max_weight: float = 3.0) -> None:
        self.weights: dict[str, float] = {k.strip(): float(v) for k, v in weights.items() if k.strip()}
        self.window = max(1, int(window))
        self.max_weight = float(max_weight)

    def scan(self, tokens: list[str], index: int) -> tuple[float, str | None]:
        """返回 (程度权重, 触发程度词)。"""
        weight = 1.0
        trigger: str | None = None
        for j in range(max(0, index - self.window), index):
            tok = tokens[j]
            if tok in self.weights:
                weight *= self.weights[tok]
                trigger = tok
        if weight > self.max_weight:
            weight = self.max_weight
        return weight, trigger


class RuleEngine:
    """把多条规则组合成一次「命中加权」计算。

    加入新规则时：实现 scan(tokens, index) 并在 apply() 中合成即可。
    """

    def __init__(self, negation: NegationRule, degree: DegreeRule) -> None:
        self.negation = negation
        self.degree = degree

    def apply(self, tokens: list[str], index: int) -> RuleHit:
        negated, neg_trigger = self.negation.scan(tokens, index)
        degree_weight, degree = self.degree.scan(tokens, index)
        return RuleHit(
            negated=negated,
            negation_trigger=neg_trigger,
            degree=degree,
            degree_weight=degree_weight,
        )
