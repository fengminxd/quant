"""Geometry helpers for two-or-three-point triangle boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from core.models import Bar
from features.basic import RegressionLine, fit_regression_line
from indicators.swing import Pivot
from patterns.triangle_validation import (
    boundary_body_breach_count,
    max_anchor_line_deviation,
    opposite_leg_rule_is_valid,
)

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


def boundary_candidates(
    points: Sequence[Pivot],
    atr: float,
    *,
    upper: bool,
    min_span: int,
    max_fit_error_atr: float,
    max_anchor_deviation_atr: float,
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
            fit_valid = line.rmse / atr <= max_fit_error_atr
            anchors_valid = (
                max_anchor_line_deviation(combo, line) / atr
                <= max_anchor_deviation_atr
            )
            if slope_valid and fit_valid and anchors_valid:
                candidates.append((combo, line))
    return candidates


def combine_boundaries(
    data: Sequence[Bar],
    all_highs: Sequence[Pivot],
    all_lows: Sequence[Pivot],
    highs: Boundary,
    lows: Boundary,
    upper: RegressionLine,
    lower: RegressionLine,
    atr: float,
    *,
    min_overlap_span: int,
    min_adjacent_anchor_span: int,
    min_compression_ratio: float,
    max_boundary_breach_atr: float,
) -> TriangleCandidate | None:
    """Combine alternating boundaries while rejecting the two-plus-two case."""

    if len(highs) == len(lows) == 2:
        return None
    if boundary_slopes_have_same_direction(upper, lower):
        return None
    if not market_legs_are_complete(highs, lows, min_adjacent_anchor_span):
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
    if boundary_body_breach_count(data, highs, upper, upper=True) > 0:
        return None
    if boundary_body_breach_count(data, lows, lower, upper=False) > 0:
        return None
    if not opposite_leg_rule_is_valid(
        data,
        same_side=lows,
        selected_opposite=highs,
        opposite_line=upper,
        upper=True,
    ):
        return None
    if not opposite_leg_rule_is_valid(
        data,
        same_side=highs,
        selected_opposite=lows,
        opposite_line=lower,
        upper=False,
    ):
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


def boundary_slopes_have_same_direction(
    upper: RegressionLine, lower: RegressionLine
) -> bool:
    """Return whether both triangle boundaries rise or both fall."""

    return upper.slope * lower.slope > 0.0


def market_legs_are_complete(
    highs: Boundary, lows: Boundary, min_adjacent_anchor_span: int = 10
) -> bool:
    """Count a new same-side confirmation only after a selected opposite anchor."""

    ordered = sorted(
        [(point.index, "high") for point in highs]
        + [(point.index, "low") for point in lows]
    )
    return all(
        left[1] != right[1] and right[0] - left[0] >= min_adjacent_anchor_span
        for left, right in zip(ordered, ordered[1:])
    )


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
