"""Reusable price-level rules for horizontal support patterns."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar


def lower_support_levels(bar: Bar) -> tuple[float, ...]:
    """Return lower prices capable of acting as support contacts."""

    return (bar.low, bar.close)


def upper_resistance_levels(bar: Bar) -> tuple[float, ...]:
    """Return upper prices capable of becoming support after a breakout."""

    return (bar.open, bar.high)


def matching_level(
    left: Sequence[float], right: Sequence[float], tolerance: float
) -> tuple[float, float] | None:
    """Return the closest aligned price and its absolute anchor error."""

    matches = [
        ((a + b) / 2.0, abs(a - b))
        for a in left
        for b in right
        if abs(a - b) <= tolerance
    ]
    return min(matches, key=lambda item: item[1]) if matches else None


def body_pierce_count(
    data: Sequence[Bar], left_index: int, right_index: int, level: float
) -> int:
    """Count candle bodies accepting price through a support level."""

    return sum(
        min(bar.open, bar.close) <= level <= max(bar.open, bar.close)
        for bar in data[left_index + 1 : right_index]
    )


def all_closes_above_level(
    data: Sequence[Bar],
    left_index: int,
    right_index: int,
    level: float,
    tolerance: float,
) -> bool:
    """Return whether the level held on every intermediate close."""

    return all(
        bar.close + tolerance >= level
        for bar in data[left_index + 1 : right_index]
    )


def first_accepted_breakout(
    data: Sequence[Bar], start_index: int, end_index: int, level: float
) -> int | None:
    """Find the first close accepted above former resistance."""

    return next(
        (
            index
            for index in range(start_index, end_index + 1)
            if data[index].close > level
        ),
        None,
    )


def post_breakout_closes_hold(
    data: Sequence[Bar],
    source_index: int,
    breakout_index: int,
    retest_index: int,
    level: float,
    tolerance: float,
) -> bool:
    """Validate acceptance above a broken level until its retest."""

    if any(
        bar.close + tolerance < level
        for bar in data[breakout_index : retest_index + 1]
    ):
        return False
    body_pierces = sum(
        min(bar.open, bar.close) <= level <= max(bar.open, bar.close)
        for bar in data[breakout_index + 1 : retest_index]
    )
    if body_pierces > 1:
        return False
    close_floor = max(data[source_index].close, data[retest_index].close)
    return not any(
        bar.low > level + tolerance and bar.close + tolerance < close_floor
        for bar in data[breakout_index + 1 : retest_index]
    )
