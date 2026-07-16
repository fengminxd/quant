from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.models import Bar
from indicators.swing import PivotDetector, SwingDetector
from patterns.inverse_head_shoulders import InverseHeadShoulders


def pattern_bars(
    *,
    timeframe: str = "1h",
    left_index: int = 10,
    head_index: int = 35,
    right_index: int = 60,
    left_price: float = 40.0,
    head_price: float = 30.0,
    right_price: float = 40.5,
    origin: datetime | None = None,
) -> list[Bar]:
    """Build a smooth inverse-head-and-shoulders price path."""

    step = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
    }[timeframe]
    left_neck = left_index + (head_index - left_index) // 2
    right_neck = head_index + (right_index - head_index) // 2
    end_index = right_index + 12
    keypoints = [
        (0, left_price + 22.0),
        (left_index, left_price),
        (left_neck, left_price + 20.0),
        (head_index, head_price),
        (right_neck, right_price + 18.0),
        (right_index, right_price),
        (right_index + 7, right_price + 23.0),
        (end_index, right_price + 25.0),
    ]
    start = origin or datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[Bar] = []
    segment = 0
    for index in range(end_index + 1):
        while segment + 1 < len(keypoints) - 1 and index > keypoints[segment + 1][0]:
            segment += 1
        x1, y1 = keypoints[segment]
        x2, y2 = keypoints[segment + 1]
        center = y1 + (y2 - y1) * (index - x1) / (x2 - x1)
        low = center - 0.1
        high = center + 0.8
        open_price = center
        close = center + 0.2
        if index == left_index:
            low = left_price
            open_price = center + 0.3
            close = center + 0.5
        elif index == head_index:
            low = head_price
            open_price = center + 0.3
            close = center + 0.5
        elif index == right_index:
            low = right_price
            open_price = center + 0.3
            close = center + 0.5
        bars.append(
            Bar(
                timestamp=(start + index * step).strftime("%Y-%m-%d %H:%M"),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0 if index < right_index + 6 else 1800.0,
                timeframe=timeframe,
            )
        )
    return bars


def detector() -> InverseHeadShoulders:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    return InverseHeadShoulders(swing_detector=swing)


@pytest.mark.parametrize("timeframe", ["15m", "1h", "4h"])
def test_rule_uses_same_bar_span_for_all_three_timeframes(timeframe: str) -> None:
    result = detector().detect(pattern_bars(timeframe=timeframe))

    assert result.detected is True
    assert result.metadata["timeframe"] == timeframe
    assert result.features["span"].value == 50.0
    assert result.features["breakout_confirmed"].value == 1.0
    assert 0.0 <= result.score <= 100.0


def test_rejects_span_below_40_bars() -> None:
    bars = pattern_bars(left_index=5, head_index=25, right_index=44)

    assert detector().detect(bars).detected is False


def test_rejects_head_that_is_not_below_both_shoulders() -> None:
    bars = pattern_bars(head_price=40.2)

    assert detector().detect(bars).detected is False


def test_rejects_shoulders_outside_atr_tolerance() -> None:
    bars = pattern_bars(right_price=52.0)

    assert detector().detect(bars).detected is False


def test_right_shoulder_requires_right_side_confirmation() -> None:
    bars = pattern_bars()

    assert detector().detect(bars[:61]).detected is False
    confirmed = detector().detect(bars[:62])
    assert confirmed.detected is True
    assert confirmed.metadata["state"] == "structure_confirmed"
    assert confirmed.features["breakout_confirmed"].value == 0.0


def test_zec_1h_regression_uses_supplied_utc_plus_8_anchors() -> None:
    origin = datetime(2026, 6, 25, 3, tzinfo=timezone.utc)
    bars = pattern_bars(
        timeframe="1h",
        left_index=10,
        head_index=91,
        right_index=142,
        left_price=386.01,
        head_price=367.77,
        right_price=385.07,
        origin=origin,
    )

    result = detector().detect(bars)

    assert result.detected is True
    assert result.metadata["state"] == "breakout_confirmed"
    assert result.features["span"].value == 132.0
    assert result.features["left_leg_span"].value == 81.0
    assert result.features["right_leg_span"].value == 51.0
    assert result.features["head_depth_atr"].value > 0.5
    assert result.features["breakout_confirmed"].value == 1.0
    assert result.score >= 75.0
    assert result.geometry["point_timestamps"] == [
        "2026-06-25 13:00",
        "2026-06-28 22:00",
        "2026-07-01 01:00",
    ]
    assert result.geometry["points"] == [
        (10, 386.01),
        (91, 367.77),
        (142, 385.07),
    ]
    utc_plus_8 = [
        (
            datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            + timedelta(hours=8)
        ).strftime("%Y-%m-%d %H:%M")
        for value in result.geometry["point_timestamps"]
    ]
    assert utc_plus_8 == [
        "2026-06-25 21:00",
        "2026-06-29 06:00",
        "2026-07-01 09:00",
    ]
    neck_left, neck_right = result.geometry["neckline_points"]
    assert 10 < neck_left[0] < 91 < neck_right[0] < 142
    assert result.geometry["breakout_index"] > 142
