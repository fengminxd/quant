"""Causal historical scanning for configured price-action patterns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from core.models import Bar, PatternResult
from core.timeframes import MIN_STRUCTURE_SPAN_BARS
from data.candles import Candle, timeframe_to_milliseconds
from indicators.swing import PivotDetector
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
from research.pattern_lines import pattern_line_groups


SCAN_TIMEFRAMES = ("1h", "4h")
UTC_PLUS_8 = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class PatternAnchor:
    """One absolute candle anchor supporting a detected structure."""

    index: int
    timestamp: int | str
    price: float


@dataclass(frozen=True)
class PatternScanEvent:
    """A de-duplicated historical structure known at one closed candle."""

    symbol: str
    timeframe: str
    pattern_id: str
    pattern_name: str
    rule: str
    score: float
    detected_timestamp: int | str
    anchors: tuple[PatternAnchor, ...]
    anchor_groups: tuple[tuple[PatternAnchor, ...], ...] = ()
    line_groups: tuple[tuple[PatternAnchor, ...], ...] = ()

    @property
    def first_anchor_index(self) -> int:
        return min(anchor.index for anchor in self.anchors)

    @property
    def last_anchor_index(self) -> int:
        return max(anchor.index for anchor in self.anchors)

    @property
    def identity(self) -> tuple[str, str, tuple[int | str, ...]]:
        """Return the stable rule-and-anchor identity used for de-duplication."""

        return self.pattern_id, self.rule, tuple(anchor.timestamp for anchor in self.anchors)


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
        self._continuous_detector = PatternDetector((Triangle(), HorizontalSupport()))
        self._scheduled_detectors = {
            "low_2": PatternDetector((ThreePointTrendlineSupport(),)),
            "low_5": PatternDetector((InverseHeadShoulders(),)),
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
        _validate_bars(bars, timeframe)
        events: list[PatternScanEvent] = []
        seen: set[tuple[str, str, tuple[int | str, ...]]] = set()
        schedules = _pivot_confirmation_schedules(bars) if self.detector is None else {}
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
        # Triangle accepts a current closed-shadow contact, while horizontal
        # support accepts a causal left-only boundary swing on the latest bar.
        # Both therefore remain eligible at every closed candle.
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
    return (
        f"symbol={event.symbol} timeframe={event.timeframe} "
        f"pattern={event.pattern_id} name={event.pattern_name!r} rule={event.rule!r} "
        f"score={event.score:.4f} anchors=[{anchors}]"
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


def _validate_bars(bars: Sequence[Bar], timeframe: str) -> None:
    mismatch = next((bar for bar in bars if bar.timeframe != timeframe), None)
    if mismatch is not None:
        raise ValueError(
            f"bar timeframe {mismatch.timeframe!r} does not match {timeframe!r}"
        )


def _pivot_confirmation_schedules(bars: Sequence[Bar]) -> dict[str, set[int]]:
    """Precompute causal raw-pivot confirmation times for event-driven scans."""

    schedules = {"low_2": set(), "low_5": set(), "high_2": set(), "high_5": set()}
    if len(bars) >= 5:
        for pivot in PivotDetector(left=2, right=2).detect(bars):
            schedules[f"{pivot.kind}_2"].add(pivot.confirmed_at)
    if len(bars) >= 11:
        for pivot in PivotDetector(left=5, right=5).detect(bars):
            schedules[f"{pivot.kind}_5"].add(pivot.confirmed_at)
    return schedules
