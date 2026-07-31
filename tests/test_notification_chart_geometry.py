from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from core.models import PatternResult
from notifications.chart import _chart_anchor_price, _draw_pattern_geometry
from notifications.models import NotificationAnchor, NotificationMatch


def match(pattern_id: str, geometry: dict[str, object]) -> NotificationMatch:
    result = PatternResult(pattern_id, pattern_id, True, 80.0, geometry=geometry)
    return NotificationMatch("TEST", "1h", 0, result)


def line_coordinates(item: NotificationMatch) -> list[tuple[list[float], list[float]]]:
    figure, axis = plt.subplots()
    _draw_pattern_geometry(axis, item)
    coordinates = [
        (list(line.get_xdata()), list(line.get_ydata()))
        for line in axis.lines
    ]
    plt.close(figure)
    return coordinates


def test_pattern_002_draws_fitted_boundaries_not_three_anchor_polylines() -> None:
    item = match(
        "PATTERN_002",
        {
            "upper_points": [(5, 20.0), (15, 18.7), (25, 18.0)],
            "lower_points": [(8, 10.0), (28, 12.0)],
            "upper_line": {"start": (5, 20.2), "end": (25, 18.2)},
            "lower_line": {"start": (8, 10.0), "end": (28, 12.0)},
        },
    )

    assert line_coordinates(item) == [
        ([5, 25], [20.2, 18.2]),
        ([8, 28], [10.0, 12.0]),
    ]


def test_pattern_005_draws_one_endpoint_line_not_contact_polyline() -> None:
    item = match(
        "PATTERN_005",
        {
            "points": [(5, 20.0), (15, 18.8), (25, 18.0)],
            "line_contacts": [(5, 20.0), (10, 19.0), (15, 19.5), (25, 18.0)],
            "line": {"start": (5, 20.0), "end": (25, 18.0)},
        },
    )

    assert line_coordinates(item) == [([5, 25], [20.0, 18.0])]


@pytest.mark.parametrize("pattern_id", ["PATTERN_007", "PATTERN_008"])
def test_head_shoulders_connects_only_actual_shoulders(pattern_id: str) -> None:
    item = match(
        pattern_id,
        {
            "points": [(5, 20.0), (15, 23.0), (25, 19.8)],
            "neckline_points": [(10, 18.0), (20, 18.3)],
        },
    )

    assert line_coordinates(item) == [([5, 25], [20.0, 19.8])]


@pytest.mark.parametrize("pattern_id", ["PATTERN_004", "PATTERN_006"])
def test_horizontal_patterns_draw_geometry_level(pattern_id: str) -> None:
    item = match(
        pattern_id,
        {"level": 20.0, "points": [(5, 20.2), (25, 19.7)]},
    )

    assert line_coordinates(item) == [([5, 25], [20.0, 20.0])]
    anchor = NotificationAnchor("P1", 5, 20.2)
    assert _chart_anchor_price(item, anchor) == 20.0
