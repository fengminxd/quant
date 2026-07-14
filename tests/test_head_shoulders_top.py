from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.models import Bar
from indicators.swing import PivotDetector
from patterns.head_shoulders_top import HeadAndShouldersTop
from tests.test_inverse_head_shoulders import pattern_bars


def top_bars(*, price_ceiling: float = 100.0, **kwargs: object) -> list[Bar]:
    """Mirror the shared bottom fixture into a positive-price top."""

    return [
        Bar(
            timestamp=bar.timestamp,
            open=price_ceiling - bar.open,
            high=price_ceiling - bar.low,
            low=price_ceiling - bar.high,
            close=price_ceiling - bar.close,
            volume=bar.volume,
            timeframe=bar.timeframe,
        )
        for bar in pattern_bars(**kwargs)
    ]


def detector() -> HeadAndShouldersTop:
    return HeadAndShouldersTop(pivot_detector=PivotDetector(left=1, right=1))


@pytest.mark.parametrize("timeframe", ["15m", "1h", "4h"])
def test_rule_uses_same_bar_span_for_all_three_timeframes(timeframe: str) -> None:
    result = detector().detect(top_bars(timeframe=timeframe))

    assert result.detected is True
    assert result.metadata["timeframe"] == timeframe
    assert result.features["span"].value == 50.0
    assert result.features["breakdown_confirmed"].value == 1.0
    assert 0.0 <= result.score <= 100.0


def test_rejects_span_below_40_bars() -> None:
    bars = top_bars(left_index=5, head_index=25, right_index=44)

    assert detector().detect(bars).detected is False


def test_rejects_head_that_is_not_above_both_shoulders() -> None:
    assert detector().detect(top_bars(head_price=40.2)).detected is False


def test_rejects_shoulders_outside_atr_tolerance() -> None:
    assert detector().detect(top_bars(right_price=52.0)).detected is False


def test_right_shoulder_requires_right_side_confirmation() -> None:
    bars = top_bars()

    assert detector().detect(bars[:61]).detected is False
    confirmed = detector().detect(bars[:62])
    assert confirmed.detected is True
    assert confirmed.metadata["state"] == "structure_confirmed"
    assert confirmed.features["breakdown_confirmed"].value == 0.0


def test_zec_4h_regression_uses_supplied_utc_plus_8_anchors() -> None:
    origin = datetime(2026, 5, 7, 12, tzinfo=timezone.utc)
    bars = top_bars(
        price_ceiling=1000.0,
        timeframe="4h",
        left_index=10,
        head_index=85,
        right_index=159,
        left_price=357.13,
        head_price=313.61,
        right_price=355.33,
        origin=origin,
    )

    result = HeadAndShouldersTop().detect(bars)

    assert result.detected is True
    assert result.features["span"].value == 149.0
    assert result.geometry["point_timestamps"] == [
        "2026-05-09 04:00",
        "2026-05-21 16:00",
        "2026-06-03 00:00",
    ]
    assert result.geometry["points"] == [
        (10, pytest.approx(642.87)),
        (85, pytest.approx(686.39)),
        (159, pytest.approx(644.67)),
    ]


def test_head_zone_prefers_later_more_symmetric_pivot() -> None:
    bars = top_bars()
    earlier = bars[29]
    bars[29] = Bar(
        timestamp=earlier.timestamp,
        open=earlier.open,
        high=70.05,
        low=earlier.low,
        close=earlier.close,
        volume=earlier.volume,
        timeframe=earlier.timeframe,
    )

    result = HeadAndShouldersTop(
        pivot_detector=PivotDetector(left=5, right=5)
    ).detect(bars)

    assert result.detected is True
    assert result.geometry["points"][1][0] == 35
    assert result.features["head_extreme_error_atr"].value > 0.0
