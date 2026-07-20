from __future__ import annotations

import pytest

from core.models import Bar
from features.basic import fit_regression_line
from indicators.swing import Pivot, PivotDetector, SwingDetector
from patterns import Triangle
from patterns.triangle_validation import boundary_body_breach_count


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
    return Triangle(swing_detector=swing, min_adjacent_anchor_span=1)


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

    before = detector().detect(bars[:23])
    after = detector().detect(bars[:24])

    assert before.detected is True
    assert before.metadata["upper_confirmation_count"] == 3
    assert before.metadata["lower_confirmation_count"] == 2
    assert after.detected is True
    assert after.metadata["upper_confirmation_count"] == 3
    assert after.metadata["lower_confirmation_count"] == 3


class StaticSwingDetector:
    def __init__(self, points: list[Pivot]) -> None:
        self.points = points

    def detect(self, data: list[Bar]) -> list[Pivot]:
        return self.points


def static_bars() -> list[Bar]:
    return [Bar(i, 15.0, 15.2, 14.8, 15.0, 1000.0, "4h") for i in range(25)]


def alternating_static_points() -> list[Pivot]:
    return [
        Pivot(2, 3, 20.0, "high"),
        Pivot(6, 7, 10.0, "low"),
        Pivot(10, 11, 19.0, "high"),
        Pivot(14, 15, 12.0, "low"),
        Pivot(18, 19, 18.0, "high"),
        Pivot(22, 23, 14.0, "low"),
    ]


@pytest.mark.parametrize("side", ["upper", "lower"])
def test_rejects_non_anchor_candle_body_beyond_boundary(side: str) -> None:
    bars = static_bars()
    if side == "upper":
        bars[12] = Bar(12, 18.6, 19.2, 18.4, 19.0, 1000.0, "4h")
    else:
        bars[12] = Bar(12, 11.2, 15.2, 11.0, 11.8, 1000.0, "4h")

    result = Triangle(
        swing_detector=StaticSwingDetector(alternating_static_points()),
        min_adjacent_anchor_span=1,
    ).detect(bars)

    assert result.detected is False


@pytest.mark.parametrize("side", ["upper", "lower"])
def test_allows_non_anchor_shadow_beyond_boundary(side: str) -> None:
    bars = static_bars()
    if side == "upper":
        bars[12] = Bar(12, 18.2, 19.2, 18.0, 18.5, 1000.0, "4h")
    else:
        bars[12] = Bar(12, 11.8, 15.2, 11.0, 12.1, 1000.0, "4h")

    result = Triangle(
        swing_detector=StaticSwingDetector(alternating_static_points()),
        min_adjacent_anchor_span=1,
    ).detect(bars)

    assert result.detected is True
    assert result.metadata["body_breach_rule"] == (
        "bodies_inside_same_and_opposite_boundaries"
    )


def test_body_breach_checks_first_last_anchor_line_not_only_regression() -> None:
    bars = static_bars()
    points = (
        Pivot(2, 3, 20.0, "high"),
        Pivot(10, 11, 19.4, "high"),
        Pivot(18, 19, 18.0, "high"),
    )
    bars[12] = Bar(12, 18.7, 19.0, 15.0, 18.82, 1000.0, "4h")
    regression = fit_regression_line(points)

    assert max(bars[12].open, bars[12].close) < regression.value_at(12)
    assert boundary_body_breach_count(bars, points, regression, upper=True) == 1


@pytest.mark.parametrize(
    ("highs", "lows", "detected", "counts"),
    [
        (
            [
                Pivot(2, 3, 20.0, "high"),
                Pivot(10, 11, 19.0, "high"),
                Pivot(18, 19, 18.0, "high"),
            ],
            [Pivot(6, 7, 10.0, "low"), Pivot(14, 15, 12.0, "low")],
            True,
            (3, 2),
        ),
        (
            [Pivot(6, 7, 20.0, "high"), Pivot(14, 15, 18.0, "high")],
            [
                Pivot(2, 3, 10.0, "low"),
                Pivot(10, 11, 10.8, "low"),
                Pivot(22, 23, 12.0, "low"),
            ],
            True,
            (2, 3),
        ),
        (
            [Pivot(2, 3, 20.0, "high"), Pivot(18, 19, 18.0, "high")],
            [Pivot(6, 7, 10.0, "low"), Pivot(14, 15, 12.0, "low")],
            False,
            None,
        ),
        (
            [
                Pivot(2, 3, 20.0, "high"),
                Pivot(10, 11, 19.0, "high"),
                Pivot(18, 19, 18.0, "high"),
            ],
            [Pivot(6, 7, 10.0, "low"), Pivot(22, 23, 12.0, "low")],
            False,
            None,
        ),
    ],
)
def test_accepts_three_plus_two_but_rejects_two_plus_two(
    highs: list[Pivot],
    lows: list[Pivot],
    detected: bool,
    counts: tuple[int, int] | None,
) -> None:
    result = Triangle(
        swing_detector=StaticSwingDetector(highs + lows),
        min_adjacent_anchor_span=1,
    ).detect(static_bars())

    assert result.detected is detected
    if counts is not None:
        assert (
            result.metadata["upper_confirmation_count"],
            result.metadata["lower_confirmation_count"],
        ) == counts


def test_default_rejects_cross_boundary_anchors_less_than_ten_bars_apart() -> None:
    result = Triangle(
        swing_detector=StaticSwingDetector(alternating_static_points())
    ).detect(static_bars())

    assert result.detected is False


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
