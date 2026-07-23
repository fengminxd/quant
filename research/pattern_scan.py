"""Causal historical scanning for configured price-action patterns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from core.models import Bar, PatternResult
from core.timeframes import MIN_STRUCTURE_SPAN_BARS, TRADING_TIMEFRAMES
from data.candles import Candle, timeframe_to_milliseconds
from factors.priority_combinations import PriorityCombinationScorer
from patterns import (
    HeadAndShouldersTop,
    HorizontalResistance,
    HorizontalSupport,
    InverseHeadShoulders,
    ThreePointTrendlineResistance,
    ThreePointTrendlineSupport,
    Triangle,
)
from patterns.detector import PatternDetector, PatternPollResult
from research.pattern_events import (
    PatternAnchor,
    PatternScanEvent,
    PriorityLevelRelation,
)
from research.pattern_lines import pattern_line_groups
from research.pattern_schedules import (
    pivot_confirmation_schedules,
    validate_scan_bars,
)


SCAN_TIMEFRAMES = TRADING_TIMEFRAMES
UTC_PLUS_8 = timezone(timedelta(hours=8))


def scan_patterns() -> tuple[object, ...]:
    """Return PATTERN_002 through PATTERN_008, explicitly excluding 001."""

    return (
        Triangle(),
        ThreePointTrendlineSupport(),
        HorizontalSupport(),
        ThreePointTrendlineResistance(),
        HorizontalResistance(),
        InverseHeadShoulders(),
        HeadAndShouldersTop(),
    )


class HistoricalPatternScanner:
    """Replay one ordered OHLCV history without exposing future candles."""

    def __init__(self, detector: PatternDetector | None = None) -> None:
        self.detector = detector
        self._continuous_detector = PatternDetector((Triangle(),))
        self._scheduled_detectors = {
            "low_2": PatternDetector((ThreePointTrendlineSupport(),)),
            "low_5": PatternDetector((HorizontalSupport(), InverseHeadShoulders())),
            "high_2": PatternDetector(
                (ThreePointTrendlineResistance(), HorizontalResistance())
            ),
            "high_5": PatternDetector((HeadAndShouldersTop(),)),
        }

    def scan(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Bar],
    ) -> list[PatternScanEvent]:
        """Scan every eligible as-of candle and keep each anchor set once."""

        if timeframe not in SCAN_TIMEFRAMES:
            raise ValueError(f"unsupported scan timeframe: {timeframe}")
        validate_scan_bars(bars, timeframe)
        events: list[PatternScanEvent] = []
        seen: set[tuple[str, str, tuple[int | str, ...]]] = set()
        schedules = (
            pivot_confirmation_schedules(bars) if self.detector is None else {}
        )
        for as_of_index in range(MIN_STRUCTURE_SPAN_BARS, len(bars)):
            results = self._poll_at(bars, timeframe, as_of_index, schedules)
            for polled in results:
                event = _to_event(symbol, bars, polled)
                if event is None or event.identity in seen:
                    continue
                seen.add(event.identity)
                events.append(event)
        return events

    def _poll_at(
        self,
        bars: Sequence[Bar],
        timeframe: str,
        as_of_index: int,
        schedules: dict[str, set[int]],
    ) -> list[PatternPollResult]:
        if self.detector is not None:
            return self.detector.poll_at(bars, timeframe, as_of_index)
        # Triangle may accept a current closed-shadow contact without waiting
        # for a pivot. Horizontal support runs only on confirmed low schedules.
        results = self._continuous_detector.poll_at(bars, timeframe, as_of_index)
        for schedule_name, detector in self._scheduled_detectors.items():
            if as_of_index in schedules[schedule_name]:
                results.extend(detector.poll_at(bars, timeframe, as_of_index))
        return results


def candles_to_bars(candles: Sequence[Candle], timeframe: str) -> list[Bar]:
    """Validate a complete closed series and convert it to framework bars."""

    if any(not candle.is_closed for candle in candles):
        raise ValueError("historical scan accepts closed candles only")
    interval_ms = timeframe_to_milliseconds(timeframe)
    ordered = sorted(candles, key=lambda candle: candle.open_time)
    for previous, current in zip(ordered, ordered[1:]):
        if current.open_time - previous.open_time != interval_ms:
            raise ValueError(
                f"non-continuous {timeframe} candles: "
                f"{previous.open_time} -> {current.open_time}"
            )
    return [candle.to_bar() for candle in ordered]


def format_utc_plus_8(timestamp: int | str) -> str:
    """Format a millisecond timestamp in the requested fixed UTC+8 zone."""

    if isinstance(timestamp, str):
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
    else:
        value = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    return value.astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M:%S UTC+8")


def event_log_line(event: PatternScanEvent) -> str:
    """Serialize the required symbol, timeframe, rule, and anchor timestamps."""

    anchors = ", ".join(format_utc_plus_8(anchor.timestamp) for anchor in event.anchors)
    sources = ", ".join(
        format_utc_plus_8(anchor.timestamp) for anchor in event.displayed_level_sources
    )
    priority = (
        f" priority_fixed=true combination={event.priority_combination_id} "
        f"combination_score={event.priority_combination_score:.4f} "
        f"matched={list(event.priority_matched_conditions)} level_sources=[{sources}]"
        if event.priority_fixed_combination
        else " priority_fixed=false"
    )
    return (
        f"symbol={event.symbol} timeframe={event.timeframe} "
        f"pattern={event.pattern_id} name={event.pattern_name!r} rule={event.rule!r} "
        f"score={event.score:.4f}{priority} anchors=[{anchors}]"
    )


def _to_event(
    symbol: str,
    bars: Sequence[Bar],
    polled: PatternPollResult,
) -> PatternScanEvent | None:
    detected_at = polled.pattern.metadata.get("detected_at_index")
    if isinstance(detected_at, (int, float)):
        absolute_detection_index = polled.window_start_index + round(float(detected_at))
        if absolute_detection_index != polled.as_of_index:
            return None
    point_groups = _geometry_point_groups(polled.pattern)
    anchors: list[PatternAnchor] = []
    anchor_groups: list[tuple[PatternAnchor, ...]] = []
    for points in point_groups:
        group: list[PatternAnchor] = []
        for local_index, price in points:
            absolute_index = polled.window_start_index + local_index
            if not 0 <= absolute_index < len(bars):
                return None
            anchor = PatternAnchor(
                absolute_index, bars[absolute_index].timestamp, float(price)
            )
            anchors.append(anchor)
            group.append(anchor)
        if group:
            anchor_groups.append(tuple(group))
    if len(anchors) < 2:
        return None
    unique = {(anchor.index, anchor.price): anchor for anchor in anchors}
    anchors = sorted(unique.values(), key=lambda anchor: (anchor.index, anchor.price))
    line_groups = tuple(
        tuple(PatternAnchor(index, bars[index].timestamp, price) for index, price in group)
        for group in pattern_line_groups(polled.pattern, bars, polled.window_start_index)
    )
    result = polled.pattern
    priority = PriorityCombinationScorer().score(
        result,
        bars,
        as_of_index=polled.as_of_index,
        window_start_index=polled.window_start_index,
    )
    priority_active = bool(priority.metadata.get("priority_fixed_combination", False))
    level_sources = tuple(
        PatternAnchor(int(index), bars[int(index)].timestamp, float(level))
        for index, level in priority.metadata.get("level_sources", ())
        if 0 <= int(index) < len(bars)
    )
    level_relations = tuple(
        PriorityLevelRelation(
            str(condition),
            str(rule_type),
            PatternAnchor(int(source), bars[int(source)].timestamp, float(level)),
            PatternAnchor(int(target), bars[int(target)].timestamp, float(level)),
            float(level),
        )
        for condition, rule_type, source, target, level in priority.metadata.get(
            "level_relations", ()
        )
        if 0 <= int(source) < len(bars) and 0 <= int(target) < len(bars)
    )
    return PatternScanEvent(
        symbol=symbol,
        timeframe=polled.timeframe,
        pattern_id=result.pattern_id,
        pattern_name=result.name,
        rule=_rule_name(result),
        score=result.score,
        detected_timestamp=bars[polled.as_of_index].timestamp,
        anchors=tuple(anchors),
        anchor_groups=tuple(anchor_groups),
        line_groups=line_groups,
        priority_fixed_combination=priority_active,
        priority_combination_id=(
            str(priority.metadata["combination_id"]) if priority_active else None
        ),
        priority_combination_score=priority.score,
        priority_matched_conditions=tuple(
            str(value)
            for value in priority.metadata.get("matched_conditions", ())
        ),
        priority_level_sources=level_sources,
        priority_level_relations=level_relations,
    )


def _geometry_point_groups(result: PatternResult) -> list[list[tuple[int, float]]]:
    geometry = result.geometry
    if result.pattern_id == "PATTERN_002":
        raw_groups = (geometry.get("upper_points", ()), geometry.get("lower_points", ()))
    else:
        raw_groups = (geometry.get("points", ()),)
    return [_numeric_points(group) for group in raw_groups if isinstance(group, Iterable)]


def _numeric_points(raw_points: Iterable[object]) -> list[tuple[int, float]]:
    return [
        (int(point[0]), float(point[1]))
        for point in raw_points
        if isinstance(point, Sequence)
        and not isinstance(point, (str, bytes))
        and len(point) >= 2
        and isinstance(point[0], (int, float))
        and isinstance(point[1], (int, float))
    ]


def _rule_name(result: PatternResult) -> str:
    if result.pattern_id == "PATTERN_002":
        return str(result.metadata.get("triangle_type", result.metadata.get("rule", result.name)))
    return str(result.metadata.get("rule_type", result.metadata.get("rule", result.name)))
