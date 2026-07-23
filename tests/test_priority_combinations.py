from __future__ import annotations

import math

import pytest

from core.models import Bar, PatternResult
from factors.priority_combinations import PriorityCombinationScorer


def flat_bars(
    timeframe: str = "1h", length: int = 160, center: float = 100.0
) -> list[Bar]:
    return [
        Bar(i, center, center + 1.0, center - 1.0, center, 1000.0, timeframe)
        for i in range(length)
    ]


def replace_bar(
    bars: list[Bar],
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> None:
    bars[index] = Bar(
        index, open_, high, low, close, 1000.0, bars[index].timeframe
    )


@pytest.mark.parametrize(
    ("pattern_id", "rule_type", "bars", "points", "combo_id", "condition"),
    [
        (
            "PATTERN_004",
            "double_swing_low",
            "support",
            [(60, 95.0), (120, 95.0)],
            "FIXED_COMBO_001",
            "second_anchor_close_above_ema99",
        ),
        (
            "PATTERN_006",
            None,
            "resistance",
            [(60, 105.0), (120, 105.0)],
            "FIXED_COMBO_002",
            "second_anchor_open_below_ema99",
        ),
    ],
)
def test_horizontal_priority_combinations_use_body_side_not_shadow_side(
    pattern_id: str,
    rule_type: str | None,
    bars: str,
    points: list[tuple[int, float]],
    combo_id: str,
    condition: str,
) -> None:
    source = flat_bars()
    if bars == "support":
        for index in (60, 120):
            replace_bar(
                source, index, open_=100.0, high=101.0, low=95.0, close=100.5
            )
    else:
        for index in (60, 120):
            replace_bar(
                source, index, open_=99.0, high=105.0, low=98.5, close=100.0
            )
    pattern = PatternResult(
        pattern_id,
        pattern_id,
        True,
        80.0,
        geometry={"points": points},
        metadata={"rule_type": rule_type} if rule_type else {},
    )

    result = PriorityCombinationScorer().score(pattern, source, as_of_index=122)

    assert result.metadata["priority_fixed_combination"] is True
    assert result.metadata["combination_id"] == combo_id
    assert result.metadata["matched_conditions"] == (condition,)
    assert result.metadata["condition_evidence"][condition][
        "shadow_crossed_ema99"
    ] is True


@pytest.mark.parametrize(
    ("pattern_id", "combo_id", "support_side"),
    [
        ("PATTERN_007", "FIXED_COMBO_003", True),
        ("PATTERN_008", "FIXED_COMBO_004", False),
    ],
)
def test_head_and_shoulders_combinations_can_match_both_conditions(
    pattern_id: str, combo_id: str, support_side: bool
) -> None:
    bars = flat_bars("15m")
    if support_side:
        for index in (60, 120):
            replace_bar(
                bars, index, open_=100.0, high=101.0, low=95.0, close=100.5
            )
        points = [(100, 97.0), (120, 95.0), (140, 98.0)]
    else:
        for index in (60, 120):
            replace_bar(
                bars, index, open_=99.0, high=105.0, low=98.5, close=100.0
            )
        points = [(100, 103.0), (120, 105.0), (140, 102.0)]
    pattern = PatternResult(
        pattern_id, pattern_id, True, 80.0, geometry={"points": points}
    )

    result = PriorityCombinationScorer().score(pattern, bars, as_of_index=142)

    assert result.score == 100.0
    assert result.metadata["combination_id"] == combo_id
    assert result.metadata["matched_count"] == 2


def test_three_point_support_combines_ema_and_breakout_retest_evidence() -> None:
    bars = flat_bars(center=104.0)
    replace_bar(bars, 60, open_=105.0, high=106.0, low=103.0, close=104.0)
    for index in range(80, 121):
        replace_bar(bars, index, open_=106.0, high=108.0, low=105.5, close=106.5)
    replace_bar(bars, 120, open_=107.0, high=108.0, low=105.0, close=107.5)
    pattern = PatternResult(
        "PATTERN_003",
        "Three Point Trendline Support",
        True,
        80.0,
        geometry={"points": [(100, 105.5), (110, 105.5), (120, 105.0)]},
    )

    result = PriorityCombinationScorer().score(pattern, bars, as_of_index=122)

    assert result.metadata["combination_id"] == "FIXED_COMBO_005"
    assert "all_three_anchors_close_above_ema99" in result.metadata[
        "matched_conditions"
    ]
    assert "third_anchor_breakout_retest_support" in result.metadata[
        "matched_conditions"
    ]
    assert result.metadata["level_sources"] == ((60, 105.5),)
    assert result.metadata["level_relations"] == (
        (
            "third_anchor_breakout_retest_support",
            "breakout_retest",
            60,
            120,
            105.5,
        ),
    )
    assert result.score == pytest.approx(66.6667)


def test_three_point_resistance_can_match_both_fixed_conditions() -> None:
    bars = flat_bars("4h")
    for index in (60, 100):
        replace_bar(
            bars, index, open_=99.0, high=105.0, low=98.5, close=100.0
        )
    replace_bar(bars, 120, open_=99.0, high=103.0, low=98.5, close=100.0)
    pattern = PatternResult(
        "PATTERN_005",
        "Three Point Trendline Resistance",
        True,
        80.0,
        geometry={"points": [(100, 105.0), (110, 104.0), (120, 103.0)]},
    )

    result = PriorityCombinationScorer().score(pattern, bars, as_of_index=122)

    assert result.score == 100.0
    assert result.metadata["combination_id"] == "FIXED_COMBO_006"
    assert result.metadata["matched_count"] == 2
    assert result.metadata["level_relations"] == (
        (
            "first_anchor_horizontal_resistance",
            "strict_two_swing_horizontal_resistance",
            60,
            100,
            105.0,
        ),
    )


def trend_bars(direction: int) -> list[Bar]:
    bars = []
    for index in range(160):
        center = 100.0 + direction * 0.1 * index + 2.0 * math.sin(
            index * math.pi / 5.0
        )
        bars.append(
            Bar(
                index,
                center,
                center + 0.3,
                center - 0.3,
                center + direction * 0.05,
                1000.0,
                "1h",
            )
        )
    return bars


@pytest.mark.parametrize(
    ("direction", "geometry", "combo_id", "ema_condition"),
    [
        (
            1,
            {
                "upper_points": [(115, 120.0), (135, 118.0)],
                "lower_points": [(110, 105.0), (125, 107.0), (140, 109.0)],
            },
            "FIXED_COMBO_007",
            "lower_third_anchor_close_above_ema99",
        ),
        (
            -1,
            {
                "upper_points": [(115, 110.0), (130, 108.0), (145, 106.0)],
                "lower_points": [(110, 90.0), (140, 92.0)],
            },
            "FIXED_COMBO_008",
            "upper_third_anchor_open_below_ema99",
        ),
    ],
)
def test_directional_triangle_combinations_require_frozen_prior_trend(
    direction: int,
    geometry: dict[str, list[tuple[int, float]]],
    combo_id: str,
    ema_condition: str,
) -> None:
    pattern = PatternResult(
        "PATTERN_002", "Triangle", True, 80.0, geometry=geometry
    )

    accepted = PriorityCombinationScorer().score(
        pattern, trend_bars(direction), as_of_index=148
    )
    rejected = PriorityCombinationScorer().score(
        pattern, trend_bars(-direction), as_of_index=148
    )

    assert accepted.metadata["combination_id"] == combo_id
    assert accepted.metadata["gate_passed"] is True
    assert ema_condition in accepted.metadata["matched_conditions"]
    assert rejected.metadata["gate_passed"] is False
    assert rejected.metadata["priority_fixed_combination"] is False
