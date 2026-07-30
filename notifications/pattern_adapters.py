"""Notification-only adapters for unconfirmed right-edge Pattern anchors."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

from core.models import Bar, PatternResult
from indicators.swing import Pivot, PivotDetector, PivotKind, SwingDetector
from patterns import (
    HeadAndShouldersTop,
    HorizontalResistance,
    HorizontalSupport,
    InverseHeadShoulders,
    ThreePointTrendlineResistance,
    ThreePointTrendlineSupport,
    Triangle,
)


class RightEdgeSwingDetector:
    """Confirmed historical swings plus unconditional final-candle anchors."""

    def __init__(
        self,
        *,
        left: int,
        right: int,
        min_bars: int,
        current_kinds: Sequence[PivotKind],
    ) -> None:
        self.base = SwingDetector(
            PivotDetector(left=left, right=right),
            min_bars=min_bars,
        )
        self.current_kinds = tuple(current_kinds)

    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        confirmed = self.base.detect(data)
        if not data:
            return confirmed
        index = len(data) - 1
        retained = [
            point
            for point in confirmed
            if point.index != index or point.kind not in self.current_kinds
        ]
        for kind in self.current_kinds:
            price = data[index].low if kind == "low" else data[index].high
            retained.append(Pivot(index, index, price, kind))
        return sorted(retained, key=lambda point: (point.index, point.kind))

    def lows(self, data: Sequence[Bar]) -> list[Pivot]:
        return [point for point in self.detect(data) if point.kind == "low"]

    def highs(self, data: Sequence[Bar]) -> list[Pivot]:
        return [point for point in self.detect(data) if point.kind == "high"]


class CurrentAnchorPattern:
    """Constrain a Pattern exposing ``detect_at`` to the latest closed candle."""

    def __init__(self, pattern: object) -> None:
        self.pattern = pattern

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return self.pattern.detect_at(data, len(data) - 1)  # type: ignore[attr-defined]


class CurrentThreePointResistance:
    """Evaluate PATTERN_005 combinations whose P3 is the latest candle."""

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return _resistance_at_close(data, three_points=True)


class CurrentHorizontalResistance:
    """Evaluate PATTERN_006 pairs whose P2 is the latest candle."""

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return _resistance_at_close(data, three_points=False)


class CurrentInverseHeadShoulders:
    """Evaluate PATTERN_007 with an unconfirmed latest right shoulder."""

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return _head_shoulders_at_close(data, top=False)


class CurrentHeadShouldersTop:
    """Evaluate PATTERN_008 with an unconfirmed latest right shoulder."""

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return _head_shoulders_at_close(data, top=True)


class _StaticSwingDetector:
    def __init__(self, points: Sequence[Pivot]) -> None:
        self.points = tuple(points)

    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        return list(self.points)

    def lows(self, data: Sequence[Bar]) -> list[Pivot]:
        return [point for point in self.points if point.kind == "low"]

    def highs(self, data: Sequence[Bar]) -> list[Pivot]:
        return [point for point in self.points if point.kind == "high"]


def notification_patterns() -> tuple[object, ...]:
    """Return PATTERN_002-008 without using central trading enablement."""

    triangle_swings = RightEdgeSwingDetector(
        left=2, right=2, min_bars=1, current_kinds=("high", "low")
    )
    trendline_lows = RightEdgeSwingDetector(
        left=2, right=2, min_bars=1, current_kinds=("low",)
    )
    support_lows = RightEdgeSwingDetector(
        left=5, right=5, min_bars=3, current_kinds=("low",)
    )
    return (
        Triangle(swing_detector=triangle_swings),  # type: ignore[arg-type]
        CurrentAnchorPattern(
            ThreePointTrendlineSupport(swing_detector=trendline_lows)  # type: ignore[arg-type]
        ),
        CurrentAnchorPattern(
            HorizontalSupport(swing_detector=support_lows)  # type: ignore[arg-type]
        ),
        CurrentThreePointResistance(),
        CurrentHorizontalResistance(),
        CurrentInverseHeadShoulders(),
        CurrentHeadShouldersTop(),
    )


def _resistance_at_close(
    data: Sequence[Bar],
    *,
    three_points: bool,
) -> PatternResult:
    detector = RightEdgeSwingDetector(
        left=2, right=2, min_bars=3, current_kinds=("high",)
    )
    highs = detector.highs(data)
    index = len(data) - 1
    current = next(point for point in highs if point.index == index)
    prior = [point for point in highs if point.index < index]
    size = 2 if three_points else 1
    results: list[PatternResult] = []
    for selected in combinations(prior, size):
        static = _StaticSwingDetector((*selected, current))
        pattern = (
            ThreePointTrendlineResistance(swing_detector=static)  # type: ignore[arg-type]
            if three_points
            else HorizontalResistance(swing_detector=static)  # type: ignore[arg-type]
        )
        result = pattern.detect(data)
        if result.detected:
            results.append(result)
    return max(
        results,
        key=lambda result: result.score,
        default=_empty_result(
            "PATTERN_005" if three_points else "PATTERN_006",
            "Three Point Trendline Resistance"
            if three_points
            else "Horizontal Resistance",
        ),
    )


def _head_shoulders_at_close(
    data: Sequence[Bar],
    *,
    top: bool,
) -> PatternResult:
    working = HeadAndShouldersTop._mirror_bars(data) if top else list(data)
    swings = SwingDetector(
        PivotDetector(left=5, right=5),
        min_bars=3,
    ).detect(working)
    index = len(working) - 1
    current = Pivot(index, index, working[index].low, "low")
    prior_lows = [
        point for point in swings if point.kind == "low" and point.index < index
    ]
    highs = [point for point in swings if point.kind == "high" and point.index < index]
    results: list[PatternResult] = []
    for left, head in combinations(prior_lows, 2):
        static = _StaticSwingDetector((left, head, current, *highs))
        pattern = (
            HeadAndShouldersTop(pivot_detector=static)  # type: ignore[arg-type]
            if top
            else InverseHeadShoulders(swing_detector=static)  # type: ignore[arg-type]
        )
        result = pattern.detect(data)
        if result.detected:
            results.append(result)
    return max(
        results,
        key=lambda result: result.score,
        default=_empty_result(
            "PATTERN_008" if top else "PATTERN_007",
            "Head and Shoulders Top" if top else "Inverse Head and Shoulders",
        ),
    )


def _empty_result(pattern_id: str, name: str) -> PatternResult:
    return PatternResult(pattern_id, name, False, 0.0)
