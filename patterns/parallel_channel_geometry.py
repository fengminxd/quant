"""Geometry search for confirmed parallel price channels."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from core.models import Bar
from indicators.swing import Pivot
from patterns.parallel_channel_contacts import BoundaryKind, ShadowContactMatcher


@dataclass(frozen=True)
class ChannelBoundary:
    """One linear boundary and its confirmed swing anchors."""

    kind: BoundaryKind
    slope: float
    intercept: float
    anchors: tuple[Pivot, ...]

    def value_at(self, index: int) -> float:
        """Project the boundary at ``index``."""

        return self.intercept + self.slope * index


@dataclass(frozen=True)
class ParallelChannelCandidate:
    """Two exactly parallel boundaries enclosing candle bodies."""

    lower: ChannelBoundary
    upper: ChannelBoundary
    start_index: int
    end_index: int
    body_violation_count: int
    wick_breach_count: int


class ParallelChannelGeometry:
    """Search same-slope shadow contacts without synthesizing pivots."""

    def __init__(
        self,
        min_channel_span: int,
        min_anchor_spacing: int,
        atr_tolerance_ratio: float,
        max_body_violations: int,
    ) -> None:
        self.min_channel_span = min_channel_span
        self.min_anchor_spacing = min_anchor_spacing
        self.max_body_violations = max_body_violations
        self.contact_matcher = ShadowContactMatcher(
            min_anchor_spacing, atr_tolerance_ratio
        )

    def best(
        self,
        data: Sequence[Bar],
        lows: Sequence[Pivot],
        highs: Sequence[Pivot],
        atr_values: Sequence[float],
        *,
        required_anchor_index: int | None = None,
    ) -> ParallelChannelCandidate | None:
        """Return the widest, best-fit valid 3+2 channel."""

        candidates = self._candidates(
            data, atr_values, "lower", lows, highs, required_anchor_index
        )
        candidates += self._candidates(
            data, atr_values, "upper", highs, lows, required_anchor_index
        )
        return max(candidates, key=lambda item: self._rank(atr_values, item)) \
            if candidates else None

    def _candidates(
        self,
        data: Sequence[Bar],
        atr_values: Sequence[float],
        primary_kind: BoundaryKind,
        primary_pivots: Sequence[Pivot],
        opposite_pivots: Sequence[Pivot],
        required_anchor_index: int | None,
    ) -> list[ParallelChannelCandidate]:
        found: list[ParallelChannelCandidate] = []
        best_span = self.min_channel_span
        seen: set[tuple[float, float]] = set()
        for first, last in combinations(primary_pivots, 2):
            if last.index - first.index < self.min_anchor_spacing:
                continue
            first_interval = self.contact_matcher.interval(
                data, atr_values, first, primary_kind
            )
            last_interval = self.contact_matcher.interval(
                data, atr_values, last, primary_kind
            )
            for first_price in first_interval:
                for last_price in last_interval:
                    slope = (last_price - first_price) / (last.index - first.index)
                    if math.isclose(slope, 0.0, abs_tol=1e-12):
                        continue
                    intercept = first_price - slope * first.index
                    key = round(slope, 12), round(intercept, 10)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates = self._parallel_candidates(
                        data,
                        atr_values,
                        primary_kind,
                        primary_pivots,
                        opposite_pivots,
                        slope,
                        intercept,
                        required_anchor_index,
                        best_span,
                    )
                    for candidate in candidates:
                        span = candidate.end_index - candidate.start_index
                        if span > best_span:
                            found.clear()
                            best_span = span
                        if span == best_span:
                            found.append(candidate)
        return found

    def _parallel_candidates(
        self,
        data: Sequence[Bar],
        atr_values: Sequence[float],
        primary_kind: BoundaryKind,
        primary_pivots: Sequence[Pivot],
        opposite_pivots: Sequence[Pivot],
        slope: float,
        intercept: float,
        required_anchor_index: int | None,
        minimum_span: int,
    ) -> list[ParallelChannelCandidate]:
        primary = self.contact_matcher.spaced(
            data,
            atr_values,
            primary_pivots,
            primary_kind,
            slope,
            intercept,
            required_anchor_index,
        )
        if len(primary) < 3:
            return []
        found: list[ParallelChannelCandidate] = []
        opposite_kind = self._opposite(primary_kind)
        options: dict[tuple[int, ...], tuple[float, tuple[Pivot, ...]]] = {}
        required_opposite = next(
            (
                point
                for point in opposite_pivots
                if point.index == required_anchor_index
            ),
            None,
        )
        required_in_primary = required_anchor_index is not None and any(
            point.index == required_anchor_index for point in primary
        )
        for parallel_intercept in self.contact_matcher.parallel_intercepts(
            data,
            atr_values,
            opposite_pivots,
            opposite_kind,
            slope,
            None if required_in_primary else required_opposite,
        ):
            if not self._ordered(primary_kind, intercept, parallel_intercept):
                continue
            opposite = self.contact_matcher.spaced(
                data, atr_values, opposite_pivots, opposite_kind,
                slope, parallel_intercept, required_anchor_index,
            )
            if len(opposite) < 2:
                continue
            key = tuple(point.index for point in opposite)
            intervals = [
                self.contact_matcher.interval(
                    data, atr_values, point, opposite_kind
                )
                for point in opposite
            ]
            lower = max(
                interval[0] - slope * point.index
                for point, interval in zip(opposite, intervals)
            )
            upper = min(
                interval[1] - slope * point.index
                for point, interval in zip(opposite, intervals)
            )
            outward = upper if opposite_kind == "upper" else lower
            options[key] = outward, opposite
        eligible = [
            option
            for option in options.values()
            if required_anchor_index is None
            or required_in_primary
            or any(point.index == required_anchor_index for point in option[1])
        ]
        if required_anchor_index is not None and eligible:
            earliest = min(
                min(point.index for point in primary + opposite)
                for _, opposite in eligible
            )
            eligible = [
                option
                for option in eligible
                if min(point.index for point in primary + option[1]) == earliest
            ]
        for parallel_intercept, opposite in eligible:
            primary_line = ChannelBoundary(primary_kind, slope, intercept, primary)
            opposite_line = ChannelBoundary(
                opposite_kind, slope, parallel_intercept, opposite
            )
            lower = primary_line if primary_kind == "lower" else opposite_line
            upper = opposite_line if primary_kind == "lower" else primary_line
            all_anchors = lower.anchors + upper.anchors
            start = min(point.index for point in all_anchors)
            end = max(point.index for point in all_anchors)
            if end - start < minimum_span:
                continue
            violations, wick_breaches = self._containment(
                data, lower, upper, start, end
            )
            if violations <= self.max_body_violations:
                found.append(
                    ParallelChannelCandidate(
                        lower, upper, start, end, violations, wick_breaches
                    )
                )
        return found

    def _containment(
        self,
        data: Sequence[Bar],
        lower: ChannelBoundary,
        upper: ChannelBoundary,
        start: int,
        end: int,
    ) -> tuple[int, int]:
        body_violations = 0
        wick_breaches = 0
        for index in range(start, end + 1):
            floor = lower.intercept + lower.slope * index
            ceiling = upper.intercept + upper.slope * index
            bar = data[index]
            if min(bar.open, bar.close) < floor - 1e-9:
                body_violations += 1
            elif max(bar.open, bar.close) > ceiling + 1e-9:
                body_violations += 1
            if body_violations > self.max_body_violations:
                return body_violations, wick_breaches
            if bar.low < floor - 1e-9 or bar.high > ceiling + 1e-9:
                wick_breaches += 1
        return body_violations, wick_breaches

    @staticmethod
    def _rank(
        atr_values: Sequence[float], candidate: ParallelChannelCandidate
    ) -> tuple[float, float, float, float]:
        anchors = candidate.lower.anchors + candidate.upper.anchors
        error = sum(
            abs(point.price - boundary.value_at(point.index))
            / max(atr_values[point.index], 1e-9)
            for boundary in (candidate.lower, candidate.upper)
            for point in boundary.anchors
        ) / len(anchors)
        return (
            float(candidate.end_index - candidate.start_index), -error,
            float(len(anchors)), -float(candidate.wick_breach_count),
        )

    @staticmethod
    def _opposite(kind: BoundaryKind) -> BoundaryKind:
        return "upper" if kind == "lower" else "lower"

    @staticmethod
    def _ordered(kind: BoundaryKind, primary: float, opposite: float) -> bool:
        return opposite > primary if kind == "lower" else primary > opposite
