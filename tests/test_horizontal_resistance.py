from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.models import Bar
from indicators.swing import PivotDetector, SwingDetector
from patterns.horizontal_resistance import HorizontalResistance


def resistance_bars(
    *,
    span: int = 43,
    timeframe: str = "1h",
    start: datetime | None = None,
    penetration: bool = False,
    open_violation: bool = False,
    open_contacts: bool = False,
) -> list[Bar]:
    """Build two swing highs separated by one confirmed swing low."""

    step = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
    }[timeframe]
    first_index = 2
    second_index = first_index + span
    origin = (start or datetime(2026, 6, 2, 9, tzinfo=timezone.utc)) - first_index * step
    middle_low_index = first_index + span // 2
    bars: list[Bar] = []
    for index in range(second_index + 2):
        open_price = 18.5
        high = 19.0
        low = 18.0
        close = 18.7
        if index == middle_low_index:
            low = 17.0
        if index == first_index:
            open_price = 20.0 if open_contacts else 19.5
            high = 20.0
            close = 19.0
        elif index == second_index:
            open_price = 20.0 if open_contacts else 19.5
            high = 20.0
            close = 19.0
        if penetration and index == middle_low_index + 2:
            high = 20.1
        if open_violation and index == middle_low_index + 2:
            open_price = 19.6
            high = max(high, 19.8)
            close = 19.4
        bars.append(
            Bar(
                timestamp=(origin + index * step).strftime("%Y-%m-%d %H:%M"),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
                timeframe=timeframe,
            )
        )
    return bars


def detector() -> HorizontalResistance:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    return HorizontalResistance(swing_detector=swing)


@pytest.mark.parametrize("timeframe", ["15m", "1h", "4h"])
def test_rule_is_timeframe_agnostic(timeframe: str) -> None:
    result = detector().detect(resistance_bars(timeframe=timeframe))

    assert result.detected is True
    assert result.metadata["timeframe"] == timeframe
    assert result.features["span"].value == 43.0
    assert result.features["penetration_count"].value == 0.0
    assert result.features["open_violation_count"].value == 0.0


def test_accepts_open_or_upper_shadow_anchor_contacts() -> None:
    wick_result = detector().detect(resistance_bars())
    open_result = detector().detect(resistance_bars(open_contacts=True))

    assert wick_result.metadata["contact_types"] == ("upper_shadow", "upper_shadow")
    assert open_result.metadata["contact_types"] == ("open", "open")


def test_rejects_intermediate_penetration() -> None:
    assert detector().detect(resistance_bars(penetration=True)).detected is False


def test_allows_intermediate_open_above_lower_anchor_open_but_below_level() -> None:
    result = detector().detect(resistance_bars(open_violation=True))

    assert result.detected is True
    assert result.features["open_violation_count"].value == 0.0


def test_second_swing_must_be_confirmed_without_lookahead() -> None:
    bars = resistance_bars()
    second_anchor_index = 45

    assert detector().detect(bars[: second_anchor_index + 1]).detected is False
    assert detector().detect(bars[: second_anchor_index + 2]).detected is True


def test_hype_example_has_at_least_40_bar_intervals() -> None:
    start = datetime(2026, 6, 2, 11, tzinfo=timezone.utc)
    result = detector().detect(resistance_bars(span=43, timeframe="1h", start=start))

    assert result.detected is True
    assert result.geometry["point_timestamps"] == [
        "2026-06-02 11:00",
        "2026-06-04 06:00",
    ]


def test_eth_example_has_at_least_40_bar_intervals() -> None:
    start = datetime(2026, 7, 7, 5, tzinfo=timezone.utc)
    result = detector().detect(
        resistance_bars(span=116, timeframe="1h", start=start)
    )

    assert result.detected is True
    assert result.features["span"].value == 116.0
    assert result.geometry["point_timestamps"] == [
        "2026-07-07 05:00",
        "2026-07-12 01:00",
    ]
