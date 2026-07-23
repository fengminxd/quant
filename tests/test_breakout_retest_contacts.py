from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Bar
from features.priority_level_context import PriorityLevelContextMatcher
from indicators.atr import average_true_range
from indicators.swing import PivotDetector, SwingDetector
from patterns.horizontal_support import HorizontalSupport
from patterns.support_levels import (
    breakout_retest_contact,
    double_bottom_contact,
)
from tests.test_patterns import horizontal_breakout_retest_bars


FIXTURE = (
    Path(__file__).parent / "fixtures" / "btc_1h_breakout_retest_contacts.json"
)
FALSE_DOUBLE_BOTTOM_FIXTURE = (
    Path(__file__).parent / "fixtures" / "btc_1h_false_double_bottom.json"
)


def _bar(timestamp: str, values: list[float]) -> Bar:
    return Bar(timestamp, *values, "1h")


def _swing_detector() -> SwingDetector:
    return SwingDetector(PivotDetector(left=1, right=1), min_bars=1)


def _legacy_matching_level(
    left: tuple[float, ...],
    right: tuple[float, ...],
    tolerance: float,
) -> tuple[float, float] | None:
    matches = [
        ((left_price + right_price) / 2.0, abs(left_price - right_price))
        for left_price in left
        for right_price in right
        if abs(left_price - right_price) <= tolerance
    ]
    return min(matches, key=lambda item: item[1]) if matches else None


def _non_overlapping_retest_bars() -> list[Bar]:
    bars = horizontal_breakout_retest_bars()
    target = bars[55]
    bars[55] = Bar(
        target.timestamp,
        21.2,
        21.4,
        20.2,
        20.5,
        target.volume,
        target.timeframe,
    )
    return bars


def _non_overlapping_double_bottom_bars() -> list[Bar]:
    bars = [
        Bar(index, 11.0, 11.8, 10.5, 11.2, 1000.0, "1h")
        for index in range(70)
    ]
    bars[5] = Bar(5, 11.1, 11.5, 10.0, 11.0, 1000.0, "1h")
    bars[30] = Bar(30, 12.0, 13.0, 11.0, 12.5, 1000.0, "1h")
    bars[55] = Bar(55, 10.4, 10.8, 9.7, 9.9, 1000.0, "1h")
    return bars


def test_btc_contacts_require_actual_traded_zone_intersection() -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results = []
    for row in rows:
        source = _bar(row["source_timestamp"], row["source"])
        retest = _bar(row["retest_timestamp"], row["retest"])
        results.append(breakout_retest_contact(source, retest))

    assert [result is not None for result in results] == [True, False, False]
    assert results[0] is not None
    assert results[0].level == pytest.approx(76_949.55)
    assert results[0].overlap_width == pytest.approx(98.9)


def test_btc_double_bottom_rejects_an_atr_bridged_contact_gap() -> None:
    row = json.loads(FALSE_DOUBLE_BOTTOM_FIXTURE.read_text(encoding="utf-8"))
    left = _bar(row["left_timestamp"], row["left"])
    right = _bar(row["right_timestamp"], row["right"])
    old_match = _legacy_matching_level(
        (left.low, left.close),
        (right.low, right.close),
        row["right_anchor_atr"] * 0.6,
    )

    assert old_match == pytest.approx((74_429.75, 100.5))
    assert double_bottom_contact(left, right) is None
    assert max(right.low, right.close) < 74_429.75 < left.low


def test_btc_reported_right_anchor_never_confirms_as_a_swing_low() -> None:
    row = json.loads(FALSE_DOUBLE_BOTTOM_FIXTURE.read_text(encoding="utf-8"))

    assert min(row["following_lows"]) < row["right"][2]


def test_pattern_and_priority_matcher_share_strict_double_bottom_contact() -> None:
    bars = _non_overlapping_double_bottom_bars()
    tolerance = average_true_range(bars[:56])[-1] * 0.6
    old_match = _legacy_matching_level(
        (bars[5].low, bars[5].close),
        (bars[55].low, bars[55].close),
        tolerance,
    )
    pattern = HorizontalSupport(_swing_detector()).detect_at(bars, 55)
    priority = PriorityLevelContextMatcher(
        _swing_detector(),
        min_span=40,
    ).double_bottom(bars, target_index=55, as_of_index=57)

    assert old_match is not None
    assert pattern.detected is False
    assert priority.matched is False


def test_atr_alignment_cannot_bridge_a_breakout_retest_contact_gap() -> None:
    bars = _non_overlapping_retest_bars()
    tolerance = average_true_range(bars[:56])[-1] * 0.6
    old_match = _legacy_matching_level(
        (bars[5].open, bars[5].high),
        (bars[55].low, bars[55].close),
        tolerance,
    )

    result = HorizontalSupport(
        _swing_detector(),
    ).detect_at(bars, 55)

    assert old_match is not None
    assert old_match[1] == pytest.approx(0.2)
    assert result.detected is False


def test_priority_combo_context_uses_the_same_strict_contact_rule() -> None:
    bars = _non_overlapping_retest_bars()
    match = PriorityLevelContextMatcher(
        _swing_detector(),
        min_span=40,
    ).breakout_retest_support(bars, target_index=55, as_of_index=57)

    assert match.matched is False


def test_detected_support_exposes_common_contact_geometry() -> None:
    result = HorizontalSupport(
        _swing_detector(),
    ).detect_at(horizontal_breakout_retest_bars(), 55)

    assert result.detected is True
    assert result.geometry["contact_points"] == [(5, 20.0), (55, 20.0)]
    assert result.features["level_error_atr"].value == 0.0
    assert result.features["hold_tolerance_atr"].value == pytest.approx(0.1)


def test_latest_valid_retest_is_preferred_for_continuous_scanning() -> None:
    bars = horizontal_breakout_retest_bars()
    earlier = bars[55]
    bars[55] = Bar(
        earlier.timestamp,
        earlier.open,
        earlier.high,
        earlier.low,
        20.5,
        earlier.volume,
        earlier.timeframe,
    )
    target = bars[60]
    bars[60] = Bar(
        target.timestamp,
        21.2,
        21.4,
        19.6,
        20.0,
        target.volume,
        target.timeframe,
    )

    result = HorizontalSupport(_swing_detector()).detect(bars[:62])

    assert result.detected is True
    assert result.geometry["points"][1][0] == 60
