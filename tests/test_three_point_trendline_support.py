from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.models import Bar
from features.basic import line_value
from features.basic import normalized_log_trend_features
from indicators.swing import Pivot
from patterns import ThreePointTrendlineSupport


def hype_support_bars(*, historical_middle_low: bool = False) -> list[Bar]:
    """Build HYPE-derived bars with an exact or historical P2 contact."""

    timeframe = timedelta(minutes=15)
    first_index, second_index, third_index = 2, 37, 92
    first_time = datetime(2026, 7, 14, 3, 15, tzinfo=timezone.utc)
    origin = first_time - first_index * timeframe
    anchor_lows: dict[int, float] = {
        first_index: 62.555,
        third_index: 64.863,
    }
    anchor_lows[second_index] = (
        63.588
        if historical_middle_low
        else anchor_lows[first_index]
        + (anchor_lows[third_index] - anchor_lows[first_index])
        * (second_index - first_index)
        / (third_index - first_index)
    )
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


def test_three_real_lower_shadow_contacts_form_support() -> None:
    result = ThreePointTrendlineSupport().detect(hype_support_bars())

    assert result.detected is True
    assert result.geometry["points"] == [
        (2, 62.555),
        (37, 63.452555555555556),
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


def test_line_may_move_inside_p1_shadow_to_reach_p3_shadow() -> None:
    result = ThreePointTrendlineSupport().detect(
        hype_support_bars(historical_middle_low=True)
    )

    assert result.detected is True
    assert result.geometry["points"] == [
        (2, 62.555),
        (37, 63.588),
        (92, 64.863),
    ]
    assert result.geometry["line_contacts"] == [
        (2, pytest.approx(62.598454545454544)),
        (37, 63.588),
        (92, pytest.approx(65.143)),
    ]
    assert result.features["p1_anchor_adjustment"].value == pytest.approx(
        0.0434545454545443
    )
    assert result.features["p2_anchor_adjustment"].value == 0.0
    assert (
        ThreePointTrendlineSupport(atr_tolerance_ratio=0.0)
        .detect(hype_support_bars(historical_middle_low=True))
        .detected
        is False
    )


def test_third_hype_anchor_requires_right_side_confirmation() -> None:
    bars = hype_support_bars()
    third_index = 92

    assert ThreePointTrendlineSupport().detect(bars[: third_index + 2]).detected is False
    assert ThreePointTrendlineSupport().detect(bars[: third_index + 3]).detected is True


def test_p3_tolerance_is_frozen_at_event_time() -> None:
    bars = hype_support_bars(historical_middle_low=True)
    detector = ThreePointTrendlineSupport()
    at_confirmation = detector.detect_at(bars, 92)
    extended = list(bars)
    for index in range(10):
        previous = extended[-1]
        extended.append(
            Bar(
                f"future-{index}",
                previous.close,
                previous.close + 100.0,
                previous.close - 100.0,
                previous.close,
                previous.volume,
                previous.timeframe,
            )
        )

    after_future_volatility = detector.detect_at(extended, 92)

    assert at_confirmation.detected is True
    assert after_future_volatility.detected is True
    assert after_future_volatility.features["tolerance"].value == pytest.approx(
        at_confirmation.features["tolerance"].value
    )


def test_raw_coordinate_angle_is_not_a_pattern_gate() -> None:
    bars = [
        Bar(
            bar.timestamp,
            bar.open * 100.0,
            bar.high * 100.0,
            bar.low * 100.0,
            bar.close * 100.0,
            bar.volume,
            bar.timeframe,
        )
        for bar in hype_support_bars()
    ]

    result = ThreePointTrendlineSupport().detect(bars)

    assert result.detected is True
    assert result.features["line_angle"].value > 50.0
    assert result.features["normalized_trend_strength"].value < 0.16


def test_normalized_trend_strength_must_not_exceed_point_sixteen() -> None:
    base = hype_support_bars()

    def shifted(drift: float) -> list[Bar]:
        return [
            Bar(
                bar.timestamp,
                bar.open + drift * index,
                bar.high + drift * index,
                bar.low + drift * index,
                bar.close + drift * index,
                bar.volume,
                bar.timeframe,
            )
            for index, bar in enumerate(base)
        ]

    accepted = shifted(0.051)
    rejected = shifted(0.052)
    accepted_result = ThreePointTrendlineSupport().detect(accepted)
    points = tuple(
        Pivot(index, index, rejected[index].low, "low")
        for index in (2, 37, 92)
    )
    rejected_strength = normalized_log_trend_features(
        rejected, points
    )["normalized_trend_strength"].value

    assert accepted_result.detected is True
    assert accepted_result.features["normalized_trend_strength"].value < 0.16
    assert rejected_strength > 0.16
    assert ThreePointTrendlineSupport().detect(rejected).detected is False


def test_anchor_may_touch_open_but_not_body_interior() -> None:
    bar = Bar(0, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)

    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 8.9) is False
    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 9.5) is True
    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 10.0) is True
    assert ThreePointTrendlineSupport._anchor_contact_is_valid(bar, 10.2) is False


def test_eth_p2_line_below_candle_low_is_not_a_contact() -> None:
    p2 = Bar(
        0,
        open=1780.0,
        high=1788.87,
        low=1777.61,
        close=1785.11,
        volume=1000.0,
    )

    assert ThreePointTrendlineSupport._anchor_contact_is_valid(
        p2, 1774.204915254237
    ) is False


def test_supplied_anchor_can_map_to_adjacent_confirmed_swing_zone() -> None:
    bars = hype_support_bars()
    requested_index = 91
    confirmed_index = 92
    requested = bars[requested_index]
    confirmed = bars[confirmed_index]
    p1 = Pivot(2, 4, bars[2].low, "low")
    p2 = Pivot(37, 39, bars[37].low, "low")
    line_low = line_value(p1, p2, requested_index)
    bars[requested_index] = Bar(
        requested.timestamp,
        line_low + 0.30,
        line_low + 0.60,
        line_low,
        line_low + 0.38,
        requested.volume,
        requested.timeframe,
    )
    bars[confirmed_index] = Bar(
        confirmed.timestamp,
        line_low + 0.28,
        line_low + 0.58,
        line_low - 0.02,
        line_low + 0.36,
        confirmed.volume,
        confirmed.timeframe,
    )
    detector = ThreePointTrendlineSupport(atr_tolerance_ratio=0.65)

    at_contact = detector.detect_anchors(
        bars[: requested_index + 1], (2, 37, requested_index)
    )
    confirmed_result = detector.detect_anchors(
        bars, (2, 37, requested_index)
    )

    assert at_contact.detected is False
    assert confirmed_result.detected is True
    assert confirmed_result.geometry["points"][-1] == (requested_index, line_low)
    assert confirmed_result.metadata["resolved_swing_indexes"] == (2, 37, 92)
    assert confirmed_result.metadata["anchor_confirmation_offsets"] == (0, 0, 1)
    assert confirmed_result.metadata["detected_at_index"] == 94


def test_eth_p1_p2_line_is_confirmed_by_p3_lower_shadow() -> None:
    origin = datetime(2026, 6, 26, 9, tzinfo=timezone(timedelta(hours=8)))
    p1, p2, p3 = 2, 108, 120
    first_low, second_low = 1510.87, 1549.16
    slope = (second_low - first_low) / (p2 - p1)
    bars: list[Bar] = []
    for index in range(p3 + 3):
        support = first_low + slope * (index - p1)
        bar = Bar(
            (origin + index * timedelta(hours=1)).isoformat(),
            support + 20.0,
            support + (80.0 if index in {55, 114} else 60.0),
            support + 10.0,
            support + 22.0,
            1_000.0,
            "1h",
        )
        if index == p1:
            bar = Bar(bar.timestamp, 1523.69, 1563.27, 1510.87, 1557.07, 1_000.0, "1h")
        elif index == p2:
            bar = Bar(bar.timestamp, 1551.81, 1566.92, 1549.16, 1566.58, 1_000.0, "1h")
        elif index == p3:
            bar = Bar(bar.timestamp, 1574.36, 1585.95, 1552.03, 1577.22, 1_000.0, "1h")
        bars.append(bar)

    before_confirmation = ThreePointTrendlineSupport(min_leg_span=10).detect(bars[:-1])
    result = ThreePointTrendlineSupport(min_leg_span=10).detect(bars)

    assert before_confirmation.detected is False
    assert ThreePointTrendlineSupport().detect(bars).detected is False
    assert result.detected is True
    assert result.geometry["points"] == [
        (p1, 1510.87),
        (p2, 1549.16),
        (p3, 1552.03),
    ]
    assert result.geometry["line"]["end"] == (
        p3,
        pytest.approx(1553.494716981132),
    )
    assert result.features["p3_projection_error"].value == pytest.approx(
        1.464716981132
    )
    assert result.features["body_violation_count"].value == 0.0
    assert (
        result.metadata["line_definition"]
        == "p1_p2_lower_shadow_contacts_projected_to_p3"
    )
