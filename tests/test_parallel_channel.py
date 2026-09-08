from __future__ import annotations

import pytest

from core.models import Bar
from patterns import ParallelChannel


def parallel_channel_bars(
    *,
    length: int = 130,
    lower_anchors: tuple[int, ...] = (5, 55, 115),
    upper_anchors: tuple[int, ...] = (30, 100),
    lower_slope: float = 0.03,
    upper_slope: float | None = None,
    body_break_index: int | None = None,
) -> list[Bar]:
    """Build an orderly rising auction between two shadow boundaries."""

    upper_drift = lower_slope if upper_slope is None else upper_slope
    bars: list[Bar] = []
    for index in range(length):
        floor = 50.0 + lower_slope * index
        ceiling = 56.0 + upper_drift * index
        low = floor + 0.8
        high = ceiling - 0.8
        open_price = floor + 2.6
        close = floor + 3.0
        if index in lower_anchors:
            low = floor
            open_price = floor + 0.6
            close = floor + 1.0
        if index in upper_anchors:
            high = ceiling
            open_price = ceiling - 0.6
            close = ceiling - 1.0
        if index == body_break_index:
            low = floor - 0.5
            open_price = floor - 0.2
            close = floor + 0.2
        bars.append(Bar(index, open_price, high, low, close, 1000.0, "1h"))
    return bars


def test_detects_parallel_channel_with_three_plus_two_anchors() -> None:
    result = ParallelChannel(atr_tolerance_ratio=0.1).detect(
        parallel_channel_bars()
    )

    assert result.detected is True
    assert result.pattern_id == "PATTERN_009"
    assert result.geometry["lower_points"] == [
        (5, pytest.approx(50.15)),
        (55, pytest.approx(51.65)),
        (115, pytest.approx(53.45)),
    ]
    assert result.geometry["upper_points"] == [
        (30, pytest.approx(56.9)),
        (100, pytest.approx(59.0)),
    ]
    assert result.features["lower_anchor_count"].value == 3.0
    assert result.features["upper_anchor_count"].value == 2.0
    assert result.features["channel_span"].value == 110.0
    assert result.features["line_slope"].value == pytest.approx(0.03)
    assert result.features["slope_difference"].value == 0.0
    assert result.features["body_violation_count"].value == 0.0
    assert 0.0 <= result.score <= 100.0
    assert result.metadata["detected_at_index"] == 117
    assert result.metadata["anchor_definition"] == "confirmed_swing_shadow_contact"


def test_channel_rejects_non_parallel_opposite_anchors() -> None:
    result = ParallelChannel(atr_tolerance_ratio=0.05).detect(
        parallel_channel_bars(upper_slope=0.06)
    )

    assert result.detected is False


def test_three_anchor_boundary_may_be_upper_and_descending() -> None:
    bars = parallel_channel_bars(
        lower_anchors=(30, 100),
        upper_anchors=(5, 55, 115),
        lower_slope=-0.03,
    )

    result = ParallelChannel(atr_tolerance_ratio=0.1).detect(bars)

    assert result.detected is True
    assert result.features["lower_anchor_count"].value == 2.0
    assert result.features["upper_anchor_count"].value == 3.0
    assert result.features["line_slope"].value == pytest.approx(-0.03)


def test_boundaries_may_share_a_slope_only_after_shadow_adjustment() -> None:
    bars = parallel_channel_bars(
        length=130,
        lower_anchors=(5, 65, 125),
        upper_anchors=(30, 100),
    )
    for index, adjustment in ((65, 0.2), (125, 0.5)):
        bar = bars[index]
        bars[index] = Bar(
            bar.timestamp,
            bar.open,
            bar.high,
            bar.low - adjustment,
            bar.close,
            bar.volume,
            bar.timeframe,
        )
    for index in (30, 100):
        bar = bars[index]
        bars[index] = Bar(
            bar.timestamp,
            bar.high - 0.05,
            bar.high,
            bar.low,
            bar.high - 0.08,
            bar.volume,
            bar.timeframe,
        )

    result = ParallelChannel().detect(bars)

    assert result.detected is True
    assert result.features["line_slope"].value == pytest.approx(0.03)
    assert result.geometry["lower_contacts"] == [
        (5, pytest.approx(50.75)),
        (65, pytest.approx(52.55)),
        (125, pytest.approx(54.35)),
    ]
    assert result.geometry["lower_contacts"] != result.geometry["lower_points"]


def test_channel_requires_at_least_one_hundred_bars_of_span() -> None:
    bars = parallel_channel_bars(
        length=100,
        lower_anchors=(5, 45, 90),
        upper_anchors=(25, 75),
    )

    assert ParallelChannel(atr_tolerance_ratio=0.1).detect(bars).detected is False


def test_channel_rejects_candle_body_outside_boundary() -> None:
    bars = parallel_channel_bars(body_break_index=80)

    assert ParallelChannel(atr_tolerance_ratio=0.1).detect(bars).detected is False


def test_last_anchor_must_be_confirmed_without_future_data() -> None:
    bars = parallel_channel_bars()
    detector = ParallelChannel(atr_tolerance_ratio=0.1)

    assert detector.detect(bars[:117]).detected is False
    assert detector.detect(bars[:118]).detected is True


def test_pattern_contract_and_configuration_validation() -> None:
    detector = ParallelChannel(atr_tolerance_ratio=0.1)
    bars = parallel_channel_bars()
    features = detector.extract_features(bars)
    result = detector.detect(bars)

    assert detector.calculate_score(features) == result.score
    assert detector.visualize(result)["geometry"] == result.geometry
    with pytest.raises(ValueError, match="span constraints"):
        ParallelChannel(min_channel_span=0)
    with pytest.raises(ValueError, match="atr_tolerance_ratio"):
        ParallelChannel(atr_tolerance_ratio=-0.1)
    with pytest.raises(ValueError, match="max_body_violations"):
        ParallelChannel(max_body_violations=-1)
