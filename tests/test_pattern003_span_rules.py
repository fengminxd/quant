from __future__ import annotations

import pytest

from indicators.swing import Pivot
from patterns import ThreePointTrendlineSupport


def points(indexes: tuple[int, int, int]) -> tuple[Pivot, Pivot, Pivot]:
    return (
        Pivot(indexes[0], indexes[0] + 2, 100.0, "low"),
        Pivot(indexes[1], indexes[1] + 2, 101.0, "low"),
        Pivot(indexes[2], indexes[2] + 2, 102.0, "low"),
    )


def test_pattern_003_accepts_exact_fifteen_fifteen_fifty_boundaries() -> None:
    detector = ThreePointTrendlineSupport()

    assert detector._passes_geometry(points((0, 15, 50))) is True
    assert detector.min_leg_span == 15
    assert detector.min_total_span == 50
    assert detector.factor.min_total_span == 50


@pytest.mark.parametrize("indexes", [(0, 14, 50), (0, 36, 50), (0, 20, 49)])
def test_pattern_003_rejects_any_span_below_the_new_minimum(
    indexes: tuple[int, int, int],
) -> None:
    assert ThreePointTrendlineSupport()._passes_geometry(points(indexes)) is False
