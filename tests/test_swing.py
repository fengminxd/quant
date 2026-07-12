from __future__ import annotations

from indicators.swing import Pivot, PivotDetector, SwingDetector, ZigZagDetector

from tests.conftest import make_bar


def test_pivot_detector_returns_confirmed_pivots_without_future_signal() -> None:
    data = [
        make_bar(0, 10, 8),
        make_bar(1, 11, 7),
        make_bar(2, 9, 8),
        make_bar(3, 12, 6),
        make_bar(4, 10, 7),
    ]

    pivots = PivotDetector(left=1, right=1).detect(data)

    low = next(pivot for pivot in pivots if pivot.index == 1 and pivot.kind == "low")
    assert low.confirmed_at == 2
    assert all(pivot.confirmed_at < len(data) for pivot in pivots)


def test_zigzag_merges_same_direction_to_more_extreme_pivot() -> None:
    pivots = [
        Pivot(1, 2, 10, "low"),
        Pivot(3, 4, 11, "low"),
        Pivot(5, 6, 15, "high"),
    ]

    turns = ZigZagDetector().detect(pivots)

    assert [(pivot.index, pivot.kind) for pivot in turns] == [(1, "low"), (5, "high")]


def test_swing_detector_applies_minimum_bar_spacing() -> None:
    data = [
        make_bar(0, 10, 8),
        make_bar(1, 12, 7),
        make_bar(2, 10, 8),
        make_bar(3, 13, 6),
        make_bar(4, 11, 8),
        make_bar(5, 14, 9),
    ]

    swings = SwingDetector(PivotDetector(left=1, right=1), min_bars=2).detect(data)

    assert all(b.index - a.index >= 2 for a, b in zip(swings, swings[1:]))
