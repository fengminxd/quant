"""Pattern-specific straight lines for historical scan charts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.models import Bar, PatternResult

LinePoint = tuple[int, float]
LineGroup = tuple[LinePoint, LinePoint]


def pattern_line_groups(
    result: PatternResult,
    bars: Sequence[Bar],
    window_start: int,
) -> tuple[LineGroup, ...]:
    """Return absolute-index straight lines without changing anchor extremes."""

    geometry = result.geometry
    if result.pattern_id == "PATTERN_002":
        return tuple(
            line
            for name in ("upper_line", "lower_line")
            if (line := _mapped_line(geometry.get(name), window_start)) is not None
        )
    points = _numeric_points(geometry.get("points", ()))
    if len(points) < 2:
        return ()
    if result.pattern_id in {"PATTERN_007", "PATTERN_008"}:
        return (_shoulder_line(result.pattern_id, points, bars, window_start),)
    if result.pattern_id in {"PATTERN_004", "PATTERN_006"}:
        level = float(geometry.get("level", (points[0][1] + points[-1][1]) / 2.0))
        return (((points[0][0] + window_start, level), (points[-1][0] + window_start, level)),)
    mapped = _mapped_line(geometry.get("line"), window_start)
    if mapped is not None:
        return (mapped,)
    return (
        (
            (points[0][0] + window_start, points[0][1]),
            (points[-1][0] + window_start, points[-1][1]),
        ),
    )


def _shoulder_line(
    pattern_id: str,
    points: Sequence[LinePoint],
    bars: Sequence[Bar],
    window_start: int,
) -> LineGroup:
    left_index = points[0][0] + window_start
    right_index = points[-1][0] + window_start
    left, right = bars[left_index], bars[right_index]
    target = (points[0][1] + points[-1][1]) / 2.0
    if pattern_id == "PATTERN_007":
        lower = max(left.low, right.low)
        upper = min(min(left.open, left.close), min(right.open, right.close))
    else:
        lower = max(max(left.open, left.close), max(right.open, right.close))
        upper = min(left.high, right.high)
    level = min(max(target, lower), upper) if lower <= upper else target
    return (left_index, level), (right_index, level)


def _mapped_line(value: object, window_start: int) -> LineGroup | None:
    if not isinstance(value, Mapping):
        return None
    start = _numeric_point(value.get("start"))
    end = _numeric_point(value.get("end"))
    if start is None or end is None:
        return None
    return (start[0] + window_start, start[1]), (end[0] + window_start, end[1])


def _numeric_points(value: object) -> list[LinePoint]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [point for item in value if (point := _numeric_point(item)) is not None]


def _numeric_point(value: object) -> LinePoint | None:
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        return int(value[0]), float(value[1])
    return None
