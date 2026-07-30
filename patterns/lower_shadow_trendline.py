"""Deterministic fitting of a support line inside three lower shadows."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Sequence

from core.models import Bar
from features.basic import line_value
from indicators.swing import Pivot


@dataclass(frozen=True)
class LowerShadowLine:
    """A P1-P2 line whose three prices lie inside the anchor shadows."""

    contacts: tuple[Pivot, Pivot, Pivot]


@dataclass(frozen=True)
class ThreePointSupportCandidate:
    """Swing lows and their fitted lower-shadow line contacts."""

    points: tuple[Pivot, Pivot, Pivot]
    line_points: tuple[Pivot, Pivot, Pivot]
    tolerance: float


def fit_lower_shadow_line(
    data: Sequence[Bar],
    points: tuple[Pivot, Pivot, Pivot],
    tolerance: float,
) -> LowerShadowLine | None:
    """Fit the least-adjusted P1-P2 line that crosses P3's lower shadow.

    Swing prices continue to identify the candle lows. Line-contact prices may
    move upward inside P1/P2's lower shadows, by at most ``tolerance``. The
    choice is deterministic: retain both lows when their projection already
    touches P3; otherwise move only the anchor that shifts the extrapolation
    toward the nearest edge of P3's eligible shadow.
    """

    if tolerance < 0.0:
        raise ValueError("tolerance must be non-negative")
    p1, p2, p3 = points
    if not (0 <= p1.index < p2.index < p3.index < len(data)):
        raise ValueError("points must be ordered inside supplied data")

    first_low, first_high = _eligible_shadow(data[p1.index], tolerance)
    second_low, second_high = _eligible_shadow(data[p2.index], tolerance)
    third_low, third_high = _eligible_shadow(data[p3.index], tolerance)
    projection_ratio = (p3.index - p1.index) / (p2.index - p1.index)
    first_price = first_low
    second_price = second_low
    projected = (
        (1.0 - projection_ratio) * first_price
        + projection_ratio * second_price
    )

    if projected < third_low and not isclose(projected, third_low, abs_tol=1e-9):
        second_price += (third_low - projected) / projection_ratio
    elif projected > third_high and not isclose(projected, third_high, abs_tol=1e-9):
        first_price += (projected - third_high) / (projection_ratio - 1.0)

    if not _inside(first_price, first_low, first_high):
        return None
    if not _inside(second_price, second_low, second_high):
        return None
    if second_price <= first_price:
        return None

    first = Pivot(p1.index, p1.confirmed_at, first_price, "low")
    second = Pivot(p2.index, p2.confirmed_at, second_price, "low")
    third_price = line_value(first, second, p3.index)
    if not _inside(third_price, third_low, third_high):
        return None
    third = Pivot(p3.index, p3.confirmed_at, third_price, "low")
    return LowerShadowLine((first, second, third))


def support_body_violation_count(
    data: Sequence[Bar],
    swing_points: tuple[Pivot, Pivot, Pivot],
    line_points: tuple[Pivot, Pivot, Pivot],
) -> int:
    """Count non-anchor candle bodies intersected by the support line."""

    p1, p2, p3 = line_points
    anchors = {point.index for point in swing_points}
    return sum(
        min(data[index].open, data[index].close)
        <= line_value(p1, p2, index)
        <= max(data[index].open, data[index].close)
        for index in range(p1.index, p3.index + 1)
        if index not in anchors
    )


def lower_shadow_contact_is_valid(bar: Bar, value: float) -> bool:
    """Return whether a price lies between the low and lower body edge."""

    return _inside(value, bar.low, min(bar.open, bar.close))


def _eligible_shadow(bar: Bar, tolerance: float) -> tuple[float, float]:
    """Return the low-side contact interval, capped by ATR tolerance."""

    return bar.low, min(min(bar.open, bar.close), bar.low + tolerance)


def _inside(value: float, lower: float, upper: float) -> bool:
    return (
        lower <= value <= upper
        or isclose(value, lower, abs_tol=1e-9)
        or isclose(value, upper, abs_tol=1e-9)
    )
