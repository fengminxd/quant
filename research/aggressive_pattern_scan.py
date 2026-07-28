"""Confirmed-pivot scanning dedicated to aggressive reference anchors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from itertools import combinations

from backtest.aggressive_entries import (
    AggressiveEntryDefinition,
    aggressive_entry_definition,
    reference_confirmation_index,
)
from core.models import Bar, PatternResult
from indicators.swing import Pivot, PivotDetector, SwingDetector
from patterns import (
    HeadAndShouldersTop,
    HorizontalResistance,
    HorizontalSupport,
    InverseHeadShoulders,
    ThreePointTrendlineSupport,
    Triangle,
)
from patterns.detector import PatternDetector
from research.pattern_events import PatternScanEvent
from research.pattern_scan import HistoricalPatternScanner


class AggressivePatternScanner:
    """Detect structures at the close that confirms their final pivot."""

    def scan(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Bar],
    ) -> list[PatternScanEvent]:
        """Return events rebased from anchor close to pivot-confirmation close."""

        detector = PatternDetector(_aggressive_patterns())
        events = HistoricalPatternScanner(detector=detector).scan(
            symbol, timeframe, bars
        )
        indexes = {bar.timestamp: index for index, bar in enumerate(bars)}
        selected: list[PatternScanEvent] = []
        for event in events:
            definition = aggressive_entry_definition(event, bars)
            detected_index = indexes[event.detected_timestamp]
            if (
                definition is None
                or definition.anchor.index != detected_index
                or not _is_confirmed_reference(definition, bars)
            ):
                continue
            confirmation_index = reference_confirmation_index(definition)
            selected.append(
                replace(
                    event,
                    detected_timestamp=bars[confirmation_index].timestamp,
                )
            )
        return selected


class _ClosedAnchorSwingDetector:
    """Confirmed historical swings plus a left-only current-bar pivot."""

    def __init__(
        self,
        min_bars: int = 1,
        left_bars: int = 2,
        right_bars: int | None = None,
    ) -> None:
        confirmed_right = left_bars if right_bars is None else right_bars
        self.base = SwingDetector(
            PivotDetector(left=left_bars, right=confirmed_right),
            min_bars=min_bars,
        )
        self.left_bars = left_bars

    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        confirmed = self.base.detect(data)
        if len(data) <= self.left_bars:
            return confirmed
        index = len(data) - 1
        bar = data[index]
        previous = data[index - self.left_bars : index]
        provisional: list[Pivot] = []
        if bar.low < min(item.low for item in previous):
            provisional.append(Pivot(index, index, bar.low, "low"))
        if bar.high > max(item.high for item in previous):
            provisional.append(Pivot(index, index, bar.high, "high"))
        return sorted(
            [*confirmed, *provisional],
            key=lambda point: (point.index, point.kind),
        )

    def lows(self, data: Sequence[Bar]) -> list[Pivot]:
        return [point for point in self.detect(data) if point.kind == "low"]

    def highs(self, data: Sequence[Bar]) -> list[Pivot]:
        return [point for point in self.detect(data) if point.kind == "high"]


class _CurrentAnchorPattern:
    """Constrain a detector exposing ``detect_at`` to the final candle."""

    def __init__(self, pattern: object) -> None:
        self.pattern = pattern

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return self.pattern.detect_at(data, len(data) - 1)  # type: ignore[attr-defined]


class _CurrentInverseHeadShoulders:
    pattern_id = "PATTERN_007"

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return _head_shoulders_at_close(data, top=False)


class _CurrentHeadShouldersTop:
    pattern_id = "PATTERN_008"

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        return _head_shoulders_at_close(data, top=True)


class _StaticPivotDetector:
    """Supply one selected right-edge shoulder combination to a detector."""

    def __init__(self, points: Sequence[Pivot]) -> None:
        self.points = tuple(points)

    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        return list(self.points)


def _head_shoulders_at_close(
    data: Sequence[Bar],
    *,
    top: bool,
) -> PatternResult:
    working = HeadAndShouldersTop._mirror_bars(data) if top else list(data)
    swings = _ClosedAnchorSwingDetector(
        min_bars=3, left_bars=5
    ).detect(working)
    index = len(data) - 1
    current = next(
        (
            point
            for point in swings
            if point.index == index and point.kind == "low"
        ),
        None,
    )
    if current is None:
        return _empty_head_result(top)
    prior_lows = [
        point for point in swings if point.kind == "low" and point.index < index
    ]
    highs = [
        point for point in swings if point.kind == "high" and point.index < index
    ]
    results: list[PatternResult] = []
    for left, head in combinations(prior_lows, 2):
        detector = _StaticPivotDetector((left, head, current, *highs))
        pattern = (
            HeadAndShouldersTop(pivot_detector=detector)  # type: ignore[arg-type]
            if top
            else InverseHeadShoulders(swing_detector=detector)  # type: ignore[arg-type]
        )
        result = pattern.detect(data)
        if result.detected:
            results.append(result)
    return max(results, key=lambda result: result.score, default=_empty_head_result(top))


def _empty_head_result(top: bool) -> PatternResult:
    return PatternResult(
        "PATTERN_008" if top else "PATTERN_007",
        "Head and Shoulders Top" if top else "Inverse Head and Shoulders",
        False,
        0.0,
    )


def _aggressive_patterns() -> tuple[object, ...]:
    trend_swings = _ClosedAnchorSwingDetector(min_bars=1, left_bars=2)
    support_swings = _ClosedAnchorSwingDetector(min_bars=3, left_bars=5)
    resistance_swings = _ClosedAnchorSwingDetector(min_bars=3, left_bars=2)
    return (
        Triangle(swing_detector=trend_swings),
        _CurrentAnchorPattern(
            ThreePointTrendlineSupport(swing_detector=trend_swings)
        ),
        _CurrentAnchorPattern(
            HorizontalSupport(swing_detector=support_swings)
        ),
        HorizontalResistance(swing_detector=resistance_swings),
        _CurrentInverseHeadShoulders(),
        _CurrentHeadShouldersTop(),
    )


def _is_confirmed_reference(
    definition: AggressiveEntryDefinition,
    bars: Sequence[Bar],
) -> bool:
    """Require the provisional final anchor to survive its right window."""

    confirmation_index = reference_confirmation_index(definition)
    if confirmation_index >= len(bars):
        return False
    pivots = PivotDetector(
        left=definition.confirmation_bars,
        right=definition.confirmation_bars,
    ).detect(bars[: confirmation_index + 1])
    return any(
        pivot.index == definition.anchor.index
        and pivot.kind == definition.pivot_kind
        for pivot in pivots
    )
