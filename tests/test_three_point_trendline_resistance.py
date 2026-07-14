from __future__ import annotations

from core.models import Bar
from indicators.swing import PivotDetector, SwingDetector
from patterns import ThreePointTrendlineResistance


def resistance_bars(body_violation: bool = False, short_span: bool = False) -> list[Bar]:
    """Build descending resistance with four interchangeable line contacts."""

    length = 76 if not short_span else 36
    anchors = (5, 30, 50, 70) if not short_span else (3, 18, 34)
    first_index = anchors[0]
    slope = -0.3
    bars: list[Bar] = []
    for index in range(length):
        line = 100.0 + slope * (index - first_index)
        if index in anchors:
            high = line
            open_price = line - 0.8
            close = line - 1.1
            low = line - 1.6
        else:
            high = line - 0.4
            open_price = line - 1.0
            close = line - 1.3
            low = line - 1.8
        if not short_span and index in {15, 38, 58}:
            high = line + 0.25
        if not short_span and index in {20, 40, 60}:
            low = line - 3.0
        if body_violation and index == 42:
            high = line + 0.6
            open_price = line + 0.2
            close = line - 0.2
            low = line - 0.7
        bars.append(Bar(index, open_price, high, low, close, 1000.0))
    return bars


def detector() -> ThreePointTrendlineResistance:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    return ThreePointTrendlineResistance(swing, atr_tolerance_ratio=0.1)


def test_allows_multiple_upper_shadow_crosses_and_point_sets() -> None:
    result = detector().detect(resistance_bars())

    assert result.detected is True
    assert result.geometry["points"] == [(5, 100.0), (30, 92.5), (70, 80.5)]
    assert {point[0] for point in result.geometry["line_contacts"]} >= {5, 30, 50, 70}
    assert result.features["line_slope"].value < 0.0
    assert result.features["line_span"].value >= 40.0
    assert result.features["leg_1_span"].value >= 10.0
    assert result.features["leg_2_span"].value >= 10.0
    assert result.features["body_violation_count"].value == 0.0
    assert result.features["upper_shadow_cross_count"].value >= 7.0
    assert result.metadata["valid_triplet_count"] > 1


def test_rejects_body_crossing() -> None:
    assert detector().detect(resistance_bars(body_violation=True)).detected is False


def test_rejects_short_span() -> None:
    assert detector().detect(resistance_bars(short_span=True)).detected is False


def test_anchor_may_touch_open_but_not_body_interior() -> None:
    bar = Bar(0, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)

    assert ThreePointTrendlineResistance._anchor_contact_is_valid(bar, 10.0) is True
    assert ThreePointTrendlineResistance._anchor_contact_is_valid(bar, 10.5) is False
