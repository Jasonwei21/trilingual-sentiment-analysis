"""命令行入口。

用法::

    python -m trilingual_sentiment "非常不好" zh
    python -m trilingual_sentiment "not very good" en --json
    python -m trilingual_sentiment "良くない" ja --lexicon my_ja.csv --lexicon-fmt csv

不带参数时运行内置示例。
"""
from __future__ import annotations

import argparse
import json
import sys

from .analyzer import SentimentAnalyzer
from .models import SentimentResult


def _format_plain(result: SentimentResult) -> str:
    lines = [
        f"文本: {result.text}",
        f"语言: {result.language}",
        f"分值: {result.score:.3f}",
        f"标签: {result.label}",
    ]
    if result.matched:
        lines.append(f"匹配词 ({len(result.matched)}):")
        for i, m in enumerate(result.matched, 1):
            parts = [f"基础 {m.base_score:.2f} → 加权 {m.weighted_score:.2f}"]
            if m.negated:
                parts.append(f"否定: {m.negation_trigger or '是'}")
            if m.degree:
                parts.append(f"程度: {m.degree} ×{m.degree_weight:g}")
            surface = f"（词面「{m.surface}」）" if m.surface and m.surface != m.word else ""
            lines.append(f"  {i}. {m.word}{surface}  " + " | ".join(parts))
    else:
        lines.append("匹配词 (0)")
    for w in result.warnings:
        lines.append(f"警告: {w}")
    return "\n".join(lines)


def _demo(analyzer: SentimentAnalyzer) -> int:
    print("== 三语情感极性判定示例 ==\n")
    cases = [
        ("非常喜欢", "zh"),
        ("非常不好", "zh"),
        ("又，今天天气不错", "zh"),
        ("良くない", "ja"),
        ("とても嬉しい", "ja"),
        ("not very good", "en"),
        ("not bad", "en"),
        ("good", "fr"),  # 未知语言代码 → 无法判断
    ]
    for text, lang in cases:
        try:
            r = analyzer.analyze(text, lang)
        except ValueError as e:
            print(f"[{lang}] {text!r}\n错误: {e}\n")
            continue
        print(_format_plain(r))
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trilingual_sentiment",
        description="三语(zh/ja/en)情感极性判定：整体分值 + 极性标签 + 匹配词明细",
    )
    parser.add_argument("text", nargs="?", help="待判定的词或句子")
    parser.add_argument("lang", nargs="?", help="语言代码: zh / ja / en")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--lexicon", help="自定义词典路径（或 HowNet 目录）")
    parser.add_argument(
        "--lexicon-fmt",
        default="csv",
        choices=["csv", "json", "hownet", "mpqa", "jp"],
        help="自定义词典格式（默认 csv）",
    )
    args = parser.parse_args(argv)

    analyzer = SentimentAnalyzer()

    if args.text is None:
        return _demo(analyzer)
    if args.lang is None:
        parser.error("需要语言代码: zh / ja / en")

    if args.lexicon:
        try:
            analyzer.load_lexicon(args.lang, args.lexicon, fmt=args.lexicon_fmt)
        except (FileNotFoundError, ValueError) as e:
            print(f"错误: 词典加载失败: {e}", file=sys.stderr)
            return 2

    try:
        result = analyzer.analyze(args.text, args.lang)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_format_plain(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
