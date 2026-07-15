from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.models import Bar
from patterns import ThreePointTrendlineSupport


def hype_support_bars() -> list[Bar]:
    """Build the reported HYPE 15m support with Binance OHLC anchor values."""

    timeframe = timedelta(minutes=15)
    first_index, second_index, third_index = 2, 37, 92
    first_time = datetime(2026, 7, 14, 3, 15, tzinfo=timezone.utc)
    origin = first_time - first_index * timeframe
    anchor_lows = {
        first_index: 62.555,
        second_index: 63.588,
        third_index: 64.863,
    }
    slope = (anchor_lows[third_index] - anchor_lows[first_index]) / (
        third_index - first_index
    )
    bars: list[Bar] = []
    for index in range(third_index + 3):
        line = anchor_lows[first_index] + slope * (index - first_index)
        if index in anchor_lows:
            low = anchor_lows[index]
            open_price = low + 0.28
            close = low + 0.36
            high = low + 0.64
        else:
            low = line + 0.35
            open_price = line + 0.55
            close = line + 0.62
            high = line + 0.85
        if index in {20, 65}:
            high = line + 1.5
        bars.append(
            Bar(
                timestamp=(origin + index * timeframe).strftime("%Y-%m-%d %H:%M"),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
                timeframe="15m",
            )
        )
    return bars


def test_hype_three_lower_shadows_form_support() -> None:
    result = ThreePointTrendlineSupport().detect(hype_support_bars())

    assert result.detected is True
    assert result.geometry["points"] == [
        (2, 62.555),
        (37, 63.588),
        (92, 64.863),
    ]
    assert result.geometry["point_timestamps"] == [
        "2026-07-14 03:15",
        "2026-07-14 12:00",
        "2026-07-15 01:45",
    ]
    assert result.features["leg_1_span"].value == 35.0
    assert result.features["leg_2_span"].value == 55.0
    assert result.features["line_span"].value == 90.0
    assert result.features["line_slope"].value > 0.0
    assert result.features["body_violation_count"].value == 0.0
    assert result.metadata["timestamp_semantics"] == "bar_open_time"


def test_third_hype_anchor_requires_right_side_confirmation() -> None:
    bars = hype_support_bars()
    third_index = 92

    assert ThreePointTrendlineSupport().detect(bars[: third_index + 2]).detected is False
    assert ThreePointTrendlineSupport().detect(bars[: third_index + 3]).detected is True


def test_anchor_may_touch_open_but_not_body_interior() -> None:
    bar = Bar(0, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)

    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 9.5, 0.5) is True
    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 10.0, 0.5) is True
    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 10.2, 0.5) is False
