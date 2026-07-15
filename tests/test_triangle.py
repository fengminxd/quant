from __future__ import annotations

import pytest

from core.models import Bar
from features.basic import fit_regression_line
from indicators.swing import Pivot, PivotDetector, SwingDetector
from patterns import Triangle


HIGH_INDEXES = (2, 10, 18)
LOW_INDEXES = (6, 14, 22)


def triangle_bars(
    upper_slope: float,
    lower_slope: float,
    *,
    breakout: str | None = None,
) -> list[Bar]:
    """Build alternating swing contacts on two configurable boundaries."""

    upper = lambda index: 20.0 + upper_slope * (index - HIGH_INDEXES[0])
    lower = lambda index: 10.0 + lower_slope * (index - LOW_INDEXES[0])
    keypoints = [
        (0, 15.0),
        (2, upper(2)),
        (6, lower(6)),
        (10, upper(10)),
        (14, lower(14)),
        (18, upper(18)),
        (22, lower(22)),
        (24, (upper(24) + lower(24)) / 2.0),
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
        if index in HIGH_INDEXES:
            high = upper(index)
            low = high - 0.7
            open_price = high - 0.4
            close = high - 0.3
        elif index in LOW_INDEXES:
            low = lower(index)
            high = low + 0.7
            open_price = low + 0.4
            close = low + 0.3
        else:
            high = center + 0.1
            low = center - 0.1
            open_price = center - 0.03
            close = center + 0.03
        bars.append(Bar(index, open_price, high, low, close, 1000.0, "4h"))
    if breakout is not None:
        index = len(bars) - 1
        boundary = upper(index) if breakout == "upside" else lower(index)
        close = boundary + 0.8 if breakout == "upside" else boundary - 0.8
        bars[index] = Bar(
            index,
            boundary,
            max(boundary + 1.0, close),
            min(boundary - 1.0, close),
            close,
            1800.0,
            "4h",
        )
    return bars


def detector() -> Triangle:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    return Triangle(swing_detector=swing)


@pytest.mark.parametrize(
    ("upper_slope", "lower_slope", "triangle_type"),
    [
        (0.0, 0.12, "ascending_triangle"),
        (-0.12, 0.0, "descending_triangle"),
        (-0.08, 0.08, "symmetrical_triangle"),
    ],
)
def test_detects_three_triangle_boundary_combinations(
    upper_slope: float,
    lower_slope: float,
    triangle_type: str,
) -> None:
    result = detector().detect(triangle_bars(upper_slope, lower_slope))

    assert result.detected is True
    assert result.metadata["triangle_type"] == triangle_type
    assert result.features["convergence_ratio"].value > 0.05
    assert result.features["upper_fit_error_atr"].value < 0.5
    assert result.features["lower_fit_error_atr"].value < 0.5


def test_rejects_parallel_box_and_diverging_boundaries() -> None:
    assert detector().detect(triangle_bars(0.0, 0.0)).detected is False
    assert detector().detect(triangle_bars(0.20, -0.20)).detected is False


@pytest.mark.parametrize("direction", ["upside", "downside"])
def test_scores_breakout_in_either_direction(direction: str) -> None:
    result = detector().detect(triangle_bars(-0.08, 0.08, breakout=direction))

    assert result.detected is True
    assert result.metadata["state"] == f"{direction}_breakout_confirmed"
    assert result.metadata["breakout_direction"] == direction
    assert result.features["breakout_strength"].value > 0.0


def test_last_boundary_requires_right_side_swing_confirmation() -> None:
    bars = triangle_bars(-0.08, 0.08)

    assert detector().detect(bars[:23]).detected is False
    assert detector().detect(bars[:24]).detected is True


def test_sui_reference_boundaries_are_inward_and_converging() -> None:
    atr = 0.012421428571428583
    highs = [
        Pivot(30, 32, 0.7797, "high"),
        Pivot(42, 44, 0.7664, "high"),
        Pivot(82, 84, 0.7484, "high"),
    ]
    lows = [
        Pivot(10, 12, 0.6767, "low"),
        Pivot(58, 60, 0.6956, "low"),
        Pivot(67, 69, 0.7114, "low"),
    ]
    upper = fit_regression_line(highs)
    lower = fit_regression_line(lows)
    overlap_start, overlap_end = 30, 67
    initial_gap = upper.value_at(overlap_start) - lower.value_at(overlap_start)
    final_gap = upper.value_at(overlap_end) - lower.value_at(overlap_end)

    assert upper.slope / atr == pytest.approx(-0.04537876, abs=1e-8)
    assert lower.slope / atr == pytest.approx(0.04325806, abs=1e-8)
    assert (initial_gap - final_gap) / initial_gap == pytest.approx(
        0.45087074, abs=1e-8
    )
