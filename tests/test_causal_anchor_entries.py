from __future__ import annotations

import math

import pytest

from backtest.anchor_outcomes import AnchorTradeOutcomeEvaluator
from core.models import Bar
from research.pattern_events import PatternAnchor, PatternScanEvent


def flat_bars(length: int = 12) -> list[Bar]:
    return [
        Bar(
            index * 3_600_000,
            100.0,
            100.5,
            99.5,
            100.0,
            1000.0,
            "1h",
        )
        for index in range(length)
    ]


def event(
    pattern_id: str,
    anchors: tuple[PatternAnchor, ...],
    bars: list[Bar],
    detected_index: int,
) -> PatternScanEvent:
    return PatternScanEvent(
        "BTC",
        "1h",
        pattern_id,
        pattern_id,
        "test_rule",
        80.0,
        bars[detected_index].timestamp,
        anchors,
        (anchors,),
        priority_fixed_combination=pattern_id == "PATTERN_006",
        priority_combination_id=(
            "FIXED_COMBO_002" if pattern_id == "PATTERN_006" else None
        ),
    )


@pytest.mark.parametrize(
    ("pattern_id", "count", "expected_position", "direction"),
    [
        ("PATTERN_004", 2, 1, "bullish"),
        ("PATTERN_006", 2, 1, "bearish"),
        ("PATTERN_007", 3, 2, "bullish"),
        ("PATTERN_003", 3, 2, "bullish"),
    ],
)
def test_standard_report_uses_first_post_detection_reclaim(
    pattern_id: str,
    count: int,
    expected_position: int,
    direction: str,
) -> None:
    bars = flat_bars()
    anchors = tuple(
        PatternAnchor(index + 1, bars[index + 1].timestamp, 100.0)
        for index in range(count)
    )
    close = 100.05 if direction == "bullish" else 99.95
    bars[6] = Bar(
        bars[6].timestamp, 100.0, 100.4, 99.6, close, 1000.0, "1h"
    )

    plan = AnchorTradeOutcomeEvaluator().plan(
        event(pattern_id, anchors, bars, detected_index=5), bars
    )

    assert plan is not None
    assert plan.structure_anchor == anchors[expected_position]
    assert plan.entry_anchor.index == 6
    assert plan.entry_price == close
    assert plan.direction == direction
    assert plan.causal_at_entry is True
    assert plan.entry_wait_bars == 1
    assert plan.entry_quality_score is not None


@pytest.mark.parametrize(
    ("pattern_id", "direction"),
    [("PATTERN_007", "bullish")],
)
def test_head_shoulders_touch_without_right_shoulder_reclaim_does_not_enter(
    pattern_id: str,
    direction: str,
) -> None:
    bars = flat_bars()
    anchors = tuple(
        PatternAnchor(index + 1, bars[index + 1].timestamp, 100.0)
        for index in range(3)
    )
    wrong_close = 99.9 if direction == "bullish" else 100.1
    bars[6] = Bar(
        bars[6].timestamp, 100.0, 100.4, 99.6, wrong_close, 1000.0, "1h"
    )
    away = 105.0 if direction == "bullish" else 95.0
    for index in range(7, 12):
        bars[index] = Bar(
            bars[index].timestamp,
            away,
            away + 0.4,
            away - 0.4,
            away,
            1000.0,
            "1h",
        )

    plan = AnchorTradeOutcomeEvaluator().plan(
        event(pattern_id, anchors, bars, detected_index=5), bars
    )

    assert plan is None


def test_standard_report_entry_may_occur_on_eleventh_waiting_bar() -> None:
    bars = flat_bars(14)
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    for index in range(3, 13):
        bars[index] = Bar(
            bars[index].timestamp, 105.0, 105.4, 104.6, 105.0, 1000.0, "1h"
        )
    bars[13] = Bar(
        bars[13].timestamp, 100.0, 100.4, 99.6, 100.1, 1000.0, "1h"
    )

    plan = AnchorTradeOutcomeEvaluator().plan(
        event("PATTERN_004", anchors, bars, detected_index=2), bars
    )

    assert plan is not None
    assert plan.entry_anchor.index == 13
    assert plan.entry_wait_bars == 11


def test_standard_report_entry_expires_after_eleven_waiting_bars() -> None:
    bars = flat_bars(15)
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    for index in range(3, 14):
        bars[index] = Bar(
            bars[index].timestamp, 105.0, 105.4, 104.6, 105.0, 1000.0, "1h"
        )
    bars[14] = Bar(
        bars[14].timestamp, 100.0, 100.4, 99.6, 100.1, 1000.0, "1h"
    )

    plan = AnchorTradeOutcomeEvaluator().plan(
        event("PATTERN_004", anchors, bars, detected_index=2), bars
    )

    assert plan is None


def trend_bars(direction: int) -> list[Bar]:
    result = []
    for index in range(160):
        center = 100.0 + direction * 0.1 * index + 2.0 * math.sin(
            index * math.pi / 5.0
        )
        result.append(
            Bar(
                index * 3_600_000,
                center,
                center + 0.3,
                center - 0.3,
                center + direction * 0.05,
                1000.0,
                "1h",
            )
        )
    return result


@pytest.mark.parametrize(
    ("direction", "upper_indexes", "lower_indexes", "structure_index", "side"),
    [
        (1, (115, 135), (110, 125, 140), 140, "bullish"),
        (-1, (115, 130, 145), (110, 140), 145, "bearish"),
    ],
)
def test_triangle_freezes_trend_and_retests_directional_third_anchor(
    direction: int,
    upper_indexes: tuple[int, ...],
    lower_indexes: tuple[int, ...],
    structure_index: int,
    side: str,
) -> None:
    bars = trend_bars(direction)
    upper = tuple(
        PatternAnchor(index, bars[index].timestamp, bars[index].high)
        for index in upper_indexes
    )
    lower = tuple(
        PatternAnchor(index, bars[index].timestamp, bars[index].low)
        for index in lower_indexes
    )
    level = lower[2].price if side == "bullish" else upper[2].price
    close = level + 0.05 if side == "bullish" else level - 0.05
    bars[151] = Bar(
        bars[151].timestamp,
        level,
        level + 0.4,
        level - 0.4,
        close,
        1000.0,
        "1h",
    )
    scan_event = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_002",
        "Triangle",
        "triangle",
        80.0,
        bars[150].timestamp,
        tuple(sorted((*upper, *lower), key=lambda anchor: anchor.index)),
        (upper, lower),
    )

    plan = AnchorTradeOutcomeEvaluator().plan(scan_event, bars)

    assert plan is not None
    assert plan.structure_anchor is not None
    assert plan.structure_anchor.index == structure_index
    assert plan.entry_anchor.index == 151
    assert plan.direction == side
    assert plan.trend_score is not None
