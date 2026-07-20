from __future__ import annotations

from indicators.swing import PivotDetector, SwingDetector
from core.models import Bar
from patterns import (
    AscendingTriangle,
    HorizontalSupport,
    PatternDetector,
    ThreePointTrendlineSupport,
    TrendlineSupport,
)

from tests.conftest import make_bar


def trendline_bars() -> list[Bar]:
    values = [
        (12, 10),
        (13, 11),
        (14, 9),
        (15, 11),
        (16, 12),
        (17, 13),
        (16, 12),
        (17, 13),
        (18, 11),
        (19, 13),
        (20, 14),
        (21, 15),
        (20, 14),
        (21, 15),
        (22, 13),
        (23, 15),
        (24, 16),
        (25, 17),
    ]
    return [make_bar(i, high, low, close=high - 0.5) for i, (high, low) in enumerate(values)]


def triangle_bars() -> list[Bar]:
    high_indexes = {2, 10, 18}
    low_indexes = {6, 14, 22}
    keypoints = [
        (0, 15.0),
        (2, 20.0),
        (6, 10.0),
        (10, 20.0),
        (14, 12.0),
        (18, 20.0),
        (22, 14.0),
        (24, 17.0),
    ]
    bars: list[Bar] = []
    segment = 0
    for index in range(25):
        while segment + 1 < len(keypoints) - 1 and index > keypoints[segment + 1][0]:
            segment += 1
        left_index, left_price = keypoints[segment]
        right_index, right_price = keypoints[segment + 1]
        center = left_price + (right_price - left_price) * (
            index - left_index
        ) / (right_index - left_index)
        if index in high_indexes:
            high = 20.0
            low = 19.3
        elif index in low_indexes:
            low = 10.0 + 0.25 * (index - 6)
            high = low + 0.7
        else:
            high = center + 0.1
            low = center - 0.1
        bars.append(make_bar(index, high, low, close=(high + low) / 2.0))
    return bars


def strict_three_point_bars(body_violation: bool = False, short_span: bool = False) -> list[Bar]:
    length = 60 if not short_span else 35
    anchor_indexes = (5, 25, 55) if not short_span else (5, 18, 34)
    anchor_lows = (10.0, 12.0, 15.0) if not short_span else (10.0, 11.3, 12.9)
    slope = (anchor_lows[-1] - anchor_lows[0]) / (anchor_indexes[-1] - anchor_indexes[0])
    bars: list[Bar] = []
    for index in range(length):
        line = anchor_lows[0] + slope * (index - anchor_indexes[0])
        if index in anchor_indexes:
            low = line
            open_price = line + 0.8
            close = line + 1.1
            high = line + 1.4
        else:
            low = line + 0.7
            open_price = line + 1.2
            close = line + 1.6
            high = line + 2.2
        if body_violation and index == 40:
            low = line - 0.2
            open_price = line - 0.1
            close = line + 0.2
            high = line + 0.5
        if index in {0, length - 1}:
            low = line + 2.0
            open_price = line + 2.4
            close = line + 2.6
            high = line + 3.0
        bars.append(
            Bar(
                timestamp=index,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
    return bars


def horizontal_double_low_bars(short_span: bool = False, pierced: bool = False) -> list[Bar]:
    length = 65 if not short_span else 35
    anchors = (5, 55) if not short_span else (5, 34)
    bars: list[Bar] = []
    for index in range(length):
        if index in anchors:
            low = 10.0
            open_price = 11.4
            close = 11.0
            high = 12.0
        elif index == 30:
            low = 10.8
            open_price = 12.5
            close = 12.6
            high = 13.0
        else:
            low = 10.8
            open_price = 11.5
            close = 11.6
            high = 12.2
        if index in {0, length - 1}:
            low = 11.2
            open_price = 11.7
            close = 11.8
            high = 12.3
        if pierced and index == 30:
            low = 9.8
            open_price = 10.3
            close = 11.5
            high = 12.0
        bars.append(Bar(index, open_price, high, low, close, 1000.0))
    return bars


def horizontal_breakout_retest_bars(extra_pierce: bool = False, weak_above_close: bool = False) -> list[Bar]:
    bars: list[Bar] = []
    for index in range(70):
        low = 20.8
        open_price = 21.4
        close = 21.5
        high = 22.0
        if index == 4:
            low = 19.0
            open_price = 21.2
            close = 21.4
            high = 21.8
        elif index == 5:
            low = 19.5
            open_price = 20.0
            close = 21.1
            high = 23.0
        elif index == 30:
            low = 19.8
            open_price = 19.8
            close = 21.4
            high = 21.8
        elif index == 55:
            low = 19.7
            open_price = 21.2
            close = 20.0
            high = 21.4
        elif weak_above_close and index == 45:
            low = 20.2
            open_price = 21.4
            close = 20.5
            high = 21.8
        if extra_pierce and index == 40:
            low = 19.9
            open_price = 19.9
            close = 21.4
            high = 21.8
        bars.append(Bar(index, open_price, high, low, close, 1000.0))
    return bars


def test_trendline_support_detects_three_rising_swing_lows() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = TrendlineSupport(swing)

    result = detector.detect(trendline_bars())

    assert result.detected is True
    assert result.features["touch_count"].value >= 3.0
    assert result.geometry["points"][0][0] == 2


def test_triangle_detects_flat_highs_and_rising_lows() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = AscendingTriangle(swing, min_adjacent_anchor_span=1)

    result = detector.detect(triangle_bars())

    assert result.detected is True
    assert result.metadata["triangle_type"] == "ascending_triangle"
    assert abs(result.features["upper_slope_atr_per_bar"].value) <= 0.02
    assert result.features["lower_slope_atr_per_bar"].value > 0.0
    assert result.features["convergence_ratio"].value > 0.0


def test_three_point_trendline_support_detects_strict_support() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = ThreePointTrendlineSupport(swing, atr_tolerance_ratio=0.1)

    result = detector.detect(strict_three_point_bars())

    assert result.detected is True
    assert result.geometry["points"] == [(5, 10.0), (25, 12.0), (55, 15.0)]
    assert result.features["body_violation_count"].value == 0.0
    assert result.features["line_span"].value >= 40.0


def test_three_point_trendline_support_rejects_body_crossing() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = ThreePointTrendlineSupport(swing, atr_tolerance_ratio=0.1)

    result = detector.detect(strict_three_point_bars(body_violation=True)[5:56])

    assert result.detected is False


def test_three_point_trendline_support_rejects_short_total_span() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = ThreePointTrendlineSupport(swing)

    result = detector.detect(strict_three_point_bars(short_span=True))

    assert result.detected is False


def test_horizontal_support_detects_double_swing_low_rule() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = HorizontalSupport(swing, atr_tolerance_ratio=0.1)

    result = detector.detect(horizontal_double_low_bars())

    assert result.detected is True
    assert result.metadata["rule_type"] == "double_swing_low"
    assert result.geometry["points"] == [(5, 10.0), (55, 10.0)]
    assert result.features["span"].value >= 40.0
    assert result.features["pierce_count"].value == 0.0


def test_horizontal_support_detects_breakout_retest_rule() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = HorizontalSupport(swing, atr_tolerance_ratio=0.1)

    result = detector.detect(horizontal_breakout_retest_bars())

    assert result.detected is True
    assert result.metadata["rule_type"] == "breakout_retest"
    assert result.geometry["points"] == [(5, 23.0), (55, 19.7)]
    assert result.features["pierce_count"].value == 1.0


def test_horizontal_support_detects_breakout_retest_at_window_boundaries() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = HorizontalSupport(swing, atr_tolerance_ratio=0.1)

    result = detector.detect(horizontal_breakout_retest_bars()[5:56])

    assert result.detected is True
    assert result.metadata["rule_type"] == "breakout_retest"
    assert result.geometry["points"] == [(0, 23.0), (50, 19.7)]


def test_horizontal_support_rejects_short_span_and_extra_pierces() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = HorizontalSupport(swing, atr_tolerance_ratio=0.1)

    assert detector.detect(horizontal_double_low_bars(short_span=True)).detected is False
    assert detector.detect(horizontal_double_low_bars(pierced=True)).detected is False
    assert detector.detect(horizontal_breakout_retest_bars(extra_pierce=True)).detected is False
    assert detector.detect(horizontal_breakout_retest_bars(weak_above_close=True)).detected is False


def test_double_low_rejects_close_below_common_support_even_within_old_tolerance() -> None:
    bars = horizontal_double_low_bars()
    bar = bars[30]
    bars[30] = Bar(
        bar.timestamp,
        9.95,
        10.05,
        9.80,
        9.95,
        bar.volume,
        bar.timeframe,
    )
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    detector = HorizontalSupport(swing, atr_tolerance_ratio=0.1)

    assert detector.detect(bars).detected is False


def test_pattern_detector_runs_registered_detectors() -> None:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=2)
    detector = PatternDetector(
        [TrendlineSupport(swing), AscendingTriangle(swing, min_adjacent_anchor_span=1)]
    )

    results = detector.detect(triangle_bars())

    assert [result.pattern_id for result in results] == ["PATTERN_001", "PATTERN_002"]
