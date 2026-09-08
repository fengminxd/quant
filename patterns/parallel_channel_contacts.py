"""Shadow-contact matching shared by parallel channel boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from core.models import Bar
from indicators.swing import Pivot

BoundaryKind = Literal["lower", "upper"]


class ShadowContactMatcher:
    """Resolve causal Swing anchors whose shadows contain a candidate line."""

    def __init__(self, min_anchor_spacing: int, atr_tolerance_ratio: float) -> None:
        self.min_anchor_spacing = min_anchor_spacing
        self.atr_tolerance_ratio = atr_tolerance_ratio

    def spaced(
        self,
        data: Sequence[Bar],
        atr_values: Sequence[float],
        pivots: Sequence[Pivot],
        kind: BoundaryKind,
        slope: float,
        intercept: float,
        required_anchor_index: int | None = None,
    ) -> tuple[Pivot, ...]:
        """Return the best spaced subset touched by one candidate line."""

        contacts = [
            pivot
            for pivot in pivots
            if self.contains(
                self.interval(data, atr_values, pivot, kind),
                intercept + slope * pivot.index,
            )
        ]
        choices: list[tuple[Pivot, ...]] = []
        for start in range(len(contacts)):
            selected = [contacts[start]]
            for pivot in contacts[start + 1 :]:
                if pivot.index - selected[-1].index >= self.min_anchor_spacing:
                    selected.append(pivot)
            choices.append(tuple(selected))
        return max(
            choices,
            key=lambda points: (
                any(point.index == required_anchor_index for point in points)
                if required_anchor_index is not None
                else True,
                len(points),
                points[-1].index - points[0].index,
            ),
            default=(),
        )

    def parallel_intercepts(
        self,
        data: Sequence[Bar],
        atr_values: Sequence[float],
        pivots: Sequence[Pivot],
        kind: BoundaryKind,
        slope: float,
        required: Pivot | None,
    ) -> set[float]:
        """Return intercept vertices, optionally constrained to one anchor."""

        values: set[float] = set()
        required_range: tuple[float, float] | None = None
        if required is not None:
            interval = self.interval(data, atr_values, required, kind)
            required_range = (
                interval[0] - slope * required.index,
                interval[1] - slope * required.index,
            )
        for pivot in pivots:
            lower, upper = self.interval(data, atr_values, pivot, kind)
            lower -= slope * pivot.index
            upper -= slope * pivot.index
            if required_range is not None:
                lower = max(lower, required_range[0])
                upper = min(upper, required_range[1])
                if lower > upper + 1e-12:
                    continue
            values.update((lower, upper))
        return values

    def interval(
        self,
        data: Sequence[Bar],
        atr_values: Sequence[float],
        pivot: Pivot,
        kind: BoundaryKind,
    ) -> tuple[float, float]:
        """Return the ATR-capped eligible shadow interval at one Swing."""

        bar = data[pivot.index]
        tolerance = atr_values[pivot.index] * self.atr_tolerance_ratio
        if kind == "lower":
            return bar.low, min(min(bar.open, bar.close), bar.low + tolerance)
        return max(max(bar.open, bar.close), bar.high - tolerance), bar.high

    @staticmethod
    def contains(interval: tuple[float, float], value: float) -> bool:
        """Return whether a projected contact lies inside an interval."""

        return interval[0] - 1e-9 <= value <= interval[1] + 1e-9
