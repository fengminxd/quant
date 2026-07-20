from __future__ import annotations

from core.models import Bar, PatternResult
from research.pattern_lines import pattern_line_groups


def bars() -> list[Bar]:
    values = [Bar(i, 15.0, 15.5, 14.5, 15.1, 1000.0, "1h") for i in range(30)]
    values[5] = Bar(5, 19.0, 20.0, 18.5, 19.2, 1000.0, "1h")
    values[15] = Bar(15, 21.0, 23.0, 20.5, 22.0, 1000.0, "1h")
    values[25] = Bar(25, 18.8, 19.8, 18.4, 19.0, 1000.0, "1h")
    return values


def test_triangle_uses_fitted_straight_lines_not_three_point_polylines() -> None:
    result = PatternResult(
        "PATTERN_002",
        "Triangle",
        True,
        80.0,
        geometry={
            "upper_points": [(2, 20.0), (6, 19.4), (10, 18.0)],
            "lower_points": [(4, 10.0), (12, 12.0)],
            "upper_line": {"start": (2, 20.2), "end": (10, 18.2)},
            "lower_line": {"start": (4, 10.0), "end": (12, 12.0)},
        },
    )

    lines = pattern_line_groups(result, bars(), window_start=3)

    assert lines == (((5, 20.2), (13, 18.2)), ((7, 10.0), (15, 12.0)))


def test_horizontal_pattern_forces_same_price_at_both_endpoints() -> None:
    result = PatternResult(
        "PATTERN_006",
        "Horizontal Resistance",
        True,
        80.0,
        geometry={"level": 20.0, "points": [(5, 20.1), (25, 19.9)]},
    )

    assert pattern_line_groups(result, bars(), 0) == (((5, 20.0), (25, 20.0)),)


def test_head_shoulders_draws_only_one_horizontal_shoulder_line() -> None:
    result = PatternResult(
        "PATTERN_008",
        "Head and Shoulders Top",
        True,
        80.0,
        geometry={"points": [(5, 20.0), (15, 23.0), (25, 19.8)]},
    )

    lines = pattern_line_groups(result, bars(), 0)

    assert len(lines) == 1
    assert lines[0][0][0] == 5
    assert lines[0][1][0] == 25
    assert lines[0][0][1] == lines[0][1][1]
