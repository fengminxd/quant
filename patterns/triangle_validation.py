"""Hard price-acceptance rules for fitted triangle boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from features.basic import RegressionLine, line_value
from indicators.swing import Pivot


def max_anchor_line_deviation(points: Sequence[Pivot], line: RegressionLine) -> float:
    """Return the largest anchor error against both boundary definitions."""

    return max(
        max(
            abs(point.price - line.value_at(point.index)),
            abs(point.price - line_value(points[0], points[-1], point.index)),
        )
        for point in points
    )


def boundary_body_breach_count(
    data: Sequence[Bar],
    points: Sequence[Pivot],
    line: RegressionLine,
    *,
    upper: bool,
    start_index: int | None = None,
    end_index: int | None = None,
    skipped_indexes: set[int] | None = None,
) -> int:
    """Count bodies beyond either the fitted line or first-last anchor line."""

    skipped = skipped_indexes or {point.index for point in points}
    start = points[0].index if start_index is None else start_index
    end = points[-1].index if end_index is None else end_index
    breaches = 0
    for index in range(start, end + 1):
        if index in skipped:
            continue
        body_edge = (
            max(data[index].open, data[index].close)
            if upper
            else min(data[index].open, data[index].close)
        )
        boundaries = (
            line.value_at(index),
            line_value(points[0], points[-1], index),
        )
        if any(
            _outside_boundary(body_edge, boundary, upper=upper)
            for boundary in boundaries
        ):
            breaches += 1
    return breaches


def opposite_leg_rule_is_valid(
    data: Sequence[Bar],
    *,
    same_side: Sequence[Pivot],
    selected_opposite: Sequence[Pivot],
    opposite_line: RegressionLine,
    upper: bool,
) -> bool:
    """Require one selected opposite anchor and wick-only tests in every leg."""

    selected_indexes = {point.index for point in selected_opposite}
    for left, right in zip(same_side, same_side[1:]):
        selected_in_leg = [
            point
            for point in selected_opposite
            if left.index < point.index < right.index
        ]
        if len(selected_in_leg) != 1:
            return False
        breaches = boundary_body_breach_count(
            data,
            selected_opposite,
            opposite_line,
            upper=upper,
            start_index=left.index,
            end_index=right.index,
            skipped_indexes=selected_indexes,
        )
        if breaches > 0:
            return False
    return True


def _outside_boundary(body_edge: float, boundary: float, *, upper: bool) -> bool:
    outside = body_edge > boundary if upper else body_edge < boundary
    return outside and not _prices_equal(body_edge, boundary)


def _prices_equal(left: float, right: float) -> bool:
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= 1e-9 * scale
