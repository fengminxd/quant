"""Telegram caption formatting for notification matches."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from notifications.models import NotificationMatch
from research.pattern_scan import format_utc_plus_8
from visualization.pattern_text import condition_label


def telegram_caption(match: NotificationMatch, bars: Sequence[Bar]) -> str:
    """Build a compact research-alert caption below Telegram's photo limit."""

    combination = match.combination_id or "-"
    conditions = ", ".join(
        condition_label(value) for value in match.matched_conditions
    ) or "-"
    anchor_lines = [
        f"{anchor.label}: {format_utc_plus_8(bars[anchor.index].timestamp)}"
        for anchor in match.anchors
        if 0 <= anchor.index < len(bars)
    ]
    lines = [
        "Price Action 实时结构提醒（末端锚点未做右侧Pivot确认）",
        f"symbol: {match.symbol}",
        f"规则: {match.pattern.pattern_id} / {match.rule}",
        f"周期: {match.timeframe}",
        f"结构分数: {match.pattern.score:.2f}",
        f"检测K线: {format_utc_plus_8(match.detected_timestamp)}",
        f"FIXED_COMBO: {combination}",
        f"组合条件: {conditions}",
        "锚点:",
        *anchor_lines,
        "样本: 最近201根已收盘K线",
    ]
    return "\n".join(lines)[:1024]
