"""三语情感极性判定工具（zh / ja / en）。

用法::

    from trilingual_sentiment import SentimentAnalyzer

    az = SentimentAnalyzer()
    r = az.analyze("非常不好", "zh")
    print(r.label, r.score, [(m.word, m.base_score, m.weighted_score) for m in r.matched])

命令行::

    python -m trilingual_sentiment "not very good" en
"""
from .analyzer import DEFAULT_DATA_DIR, LanguageProfile, SentimentAnalyzer
from .detect import LanguageGuess, detect_language
from .lexicon import LexiconError, SentimentLexicon
from .models import (
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    LABEL_UNKNOWN,
    MatchedWord,
    SentimentResult,
)
from .rules import DegreeRule, NegationRule, RuleEngine, RuleHit

__all__ = [
    "SentimentAnalyzer",
    "LanguageProfile",
    "DEFAULT_DATA_DIR",
    "SentimentLexicon",
    "LexiconError",
    "SentimentResult",
    "MatchedWord",
    "detect_language",
    "LanguageGuess",
    "LABEL_POSITIVE",
    "LABEL_NEGATIVE",
    "LABEL_NEUTRAL",
    "LABEL_UNKNOWN",
    "NegationRule",
    "DegreeRule",
    "RuleEngine",
    "RuleHit",
]

__version__ = "1.0.0"
