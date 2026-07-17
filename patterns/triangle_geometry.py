"""Geometry helpers for two-or-three-point triangle boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from core.models import Bar
from features.basic import RegressionLine, fit_regression_line
from indicators.swing import Pivot

Boundary = tuple[Pivot, ...]
BoundaryFit = tuple[Boundary, RegressionLine]


@dataclass(frozen=True)
class TriangleCandidate:
    """Two converging boundaries with at least five independent confirmations."""

    highs: Boundary
    lows: Boundary
    upper: RegressionLine
    lower: RegressionLine
    overlap_start: int
    overlap_end: int
    compression_ratio: float
    atr: float


def cluster_boundary_pivots(
    data: Sequence[Bar],
    points: Sequence[Pivot],
    atr: float,
    *,
    upper: bool,
    cluster_bars: int,
    shadow_ratio: float,
    price_tolerance_atr: float,
) -> list[Pivot]:
    """Collapse nearby same-side pivots and retain an earlier wick contact."""

    groups: list[list[Pivot]] = []
    for point in points:
        if groups and point.index - groups[-1][-1].index <= cluster_bars:
            groups[-1].append(point)
        else:
            groups.append([point])
    return [
        _representative(
            data,
            group,
            atr,
            upper=upper,
            cluster_bars=cluster_bars,
            shadow_ratio=shadow_ratio,
            price_tolerance_atr=price_tolerance_atr,
        )
        for group in groups
    ]


def include_closed_shadow_contacts(
    data: Sequence[Bar],
    points: Sequence[Pivot],
    *,
    upper: bool,
    lookback_bars: int,
    shadow_ratio: float,
    allowed_indexes: Sequence[int] | None = None,
) -> list[Pivot]:
    """Add recent closed wick contacts without waiting for right-side pivots."""

    existing = {point.index for point in points}
    contacts = list(points)
    start = max(0, len(data) - lookback_bars - 1)
    indexes = range(start, len(data)) if allowed_indexes is None else allowed_indexes
    for index in indexes:
        if index in existing:
            continue
        bar = data[index]
        candle_range = max(bar.high - bar.low, 1e-12)
        body_top = max(bar.open, bar.close)
        body_bottom = min(bar.open, bar.close)
        shadow = bar.high - body_top if upper else body_bottom - bar.low
        if shadow / candle_range < shadow_ratio:
            continue
        price = bar.high if upper else bar.low
        contacts.append(Pivot(index, index, price, "high" if upper else "low"))
    return sorted(contacts, key=lambda point: (point.index, point.confirmed_at))


def boundary_candidates(
    points: Sequence[Pivot],
    atr: float,
    *,
    upper: bool,
    min_span: int,
    max_fit_error_atr: float,
    horizontal_slope_atr_per_bar: float,
) -> list[BoundaryFit]:
    """Fit every eligible two-point and three-point boundary."""

    candidates: list[BoundaryFit] = []
    for count in (2, 3):
        for combo in combinations(points, count):
            if combo[-1].index - combo[0].index < min_span:
                continue
            line = fit_regression_line(combo)
            normalized_slope = line.slope / atr
            slope_valid = (
                normalized_slope <= horizontal_slope_atr_per_bar
                if upper
                else normalized_slope >= -horizontal_slope_atr_per_bar
            )
            if slope_valid and line.rmse / atr <= max_fit_error_atr:
                candidates.append((combo, line))
    return candidates


def combine_boundaries(
    all_highs: Sequence[Pivot],
    all_lows: Sequence[Pivot],
    highs: Boundary,
    lows: Boundary,
    upper: RegressionLine,
    lower: RegressionLine,
    atr: float,
    *,
    min_overlap_span: int,
    min_compression_ratio: float,
    max_boundary_breach_atr: float,
) -> TriangleCandidate | None:
    """Combine alternating boundaries while rejecting the two-plus-two case."""

    if len(highs) == len(lows) == 2:
        return None
    if not _alternates(highs, lows):
        return None
    overlap_start = max(highs[0].index, lows[0].index)
    overlap_end = min(highs[-1].index, lows[-1].index)
    if overlap_end - overlap_start < min_overlap_span:
        return None
    gap_start = upper.value_at(overlap_start) - lower.value_at(overlap_start)
    gap_end = upper.value_at(overlap_end) - lower.value_at(overlap_end)
    if gap_start <= 0.0 or gap_end <= 0.0:
        return None
    compression = (gap_start - gap_end) / gap_start
    if compression < min_compression_ratio:
        return None
    tolerance = max_boundary_breach_atr * atr
    if any(
        point.price > upper.value_at(point.index) + tolerance
        for point in all_highs
        if highs[0].index <= point.index <= highs[-1].index
    ):
        return None
    if any(
        point.price < lower.value_at(point.index) - tolerance
        for point in all_lows
        if lows[0].index <= point.index <= lows[-1].index
    ):
        return None
    return TriangleCandidate(
        highs, lows, upper, lower, overlap_start, overlap_end, compression, atr
    )


def _alternates(highs: Boundary, lows: Boundary) -> bool:
    """Require each same-side confirmation to be separated by the other side."""

    ordered = sorted(
        [(point.index, "high") for point in highs]
        + [(point.index, "low") for point in lows]
    )
    return all(left[1] != right[1] for left, right in zip(ordered, ordered[1:]))


def candidate_rank(candidate: TriangleCandidate) -> tuple[float, ...]:
    """Prefer the latest active structure, then overlap and evidence quality."""

    latest_anchor = max(candidate.highs[-1].index, candidate.lows[-1].index)
    overlap = candidate.overlap_end - candidate.overlap_start
    confirmations = len(candidate.highs) + len(candidate.lows)
    fit_error = candidate.upper.rmse + candidate.lower.rmse
    total_span = max(candidate.highs[-1].index, candidate.lows[-1].index) - min(
        candidate.highs[0].index, candidate.lows[0].index
    )
    return (
        float(latest_anchor),
        float(overlap),
        float(confirmations),
        -fit_error,
        candidate.compression_ratio,
        float(total_span),
    )


def line_geometry(
    line: RegressionLine, points: Sequence[Pivot]
) -> dict[str, tuple[int, float]]:
    """Serialize a fitted boundary at its first and last anchors."""

    return {
        "start": (points[0].index, line.value_at(points[0].index)),
        "end": (points[-1].index, line.value_at(points[-1].index)),
    }


def apex_index(candidate: TriangleCandidate) -> float | None:
    """Return the projected boundary intersection in window-local bar units."""

    slope_difference = candidate.upper.slope - candidate.lower.slope
    if abs(slope_difference) <= 1e-12:
        return None
    return (candidate.lower.intercept - candidate.upper.intercept) / slope_difference


def _representative(
    data: Sequence[Bar],
    group: Sequence[Pivot],
    atr: float,
    *,
    upper: bool,
    cluster_bars: int,
    shadow_ratio: float,
    price_tolerance_atr: float,
) -> Pivot:
    extreme = (max if upper else min)(group, key=lambda point: point.price)
    confirmed_at = max(point.confirmed_at for point in group)
    tolerance = price_tolerance_atr * atr
    for index in range(max(0, extreme.index - cluster_bars), extreme.index + 1):
        bar = data[index]
        candle_range = max(bar.high - bar.low, 1e-12)
        body_top = max(bar.open, bar.close)
        body_bottom = min(bar.open, bar.close)
        shadow = bar.high - body_top if upper else body_bottom - bar.low
        close_to_extreme = (
            bar.high >= extreme.price - tolerance
            if upper
            else bar.low <= extreme.price + tolerance
        )
        if close_to_extreme and shadow / candle_range >= shadow_ratio:
            price = bar.high if upper else bar.low
            return Pivot(index, confirmed_at, price, extreme.kind)
    return Pivot(extreme.index, confirmed_at, extreme.price, extreme.kind)
