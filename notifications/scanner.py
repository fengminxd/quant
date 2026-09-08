"""Latest-candle scanner isolated from trading and report policy gates."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from core.models import Bar, FactorResult, PatternResult
from factors.priority_combinations import PriorityFixedCombinationScore
from features.priority_combinations import PriorityCombinationFeatureExtractor
from notifications.config import (
    HISTORY_BARS,
    NOTIFICATION_TIMEFRAMES,
    notification_window_is_ready,
)
from notifications.models import NotificationMatch
from notifications.pattern_adapters import (
    notification_channel_patterns,
    notification_patterns,
)
from patterns.detector import PatternDetector


_PATTERN_009_TIMEFRAMES = frozenset({"4h"})


class NotificationPriorityScorer:
    """Evaluate all fixed combinations, including notification-only COMBO_006."""

    def __init__(
        self,
        extractor: PriorityCombinationFeatureExtractor | None = None,
    ) -> None:
        self.extractor = extractor or PriorityCombinationFeatureExtractor()

    def score(
        self,
        pattern: PatternResult,
        bars: Sequence[Bar],
    ) -> FactorResult | None:
        """Return an active combination without consulting trading policy."""

        feature_set = self.extractor.extract(
            pattern,
            bars,
            as_of_index=len(bars) - 1,
            window_start_index=0,
        )
        if feature_set is None:
            return None
        result = PriorityFixedCombinationScore(feature_set).calculate(
            feature_set.features
        )
        return result if result.metadata.get("active") else None


class NotificationPatternScanner:
    """Detect notification patterns, with PATTERN_009 restricted to 4h."""

    def __init__(
        self,
        patterns: Iterable[object] | None = None,
        priority_scorer: NotificationPriorityScorer | None = None,
    ) -> None:
        selected = notification_patterns() if patterns is None else patterns
        self.detector = PatternDetector(selected)  # type: ignore[arg-type]
        extended = notification_channel_patterns() if patterns is None else ()
        self.extended_detector = PatternDetector(extended)  # type: ignore[arg-type]
        self.priority_scorer = priority_scorer or NotificationPriorityScorer()

    def scan(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Bar],
    ) -> list[NotificationMatch]:
        """Return structures whose unconfirmed final anchor is the latest candle."""

        if timeframe not in NOTIFICATION_TIMEFRAMES:
            raise ValueError(f"notification timeframe must be one of {NOTIFICATION_TIMEFRAMES}")
        if not notification_window_is_ready(timeframe, len(bars)):
            raise ValueError(
                "notification scan requires exactly 201 bars for 15m/1h "
                "or at least 201 bars for 4h"
            )
        if any(bar.timeframe not in (None, timeframe) for bar in bars):
            raise ValueError("bar timeframe does not match notification timeframe")
        last_index = len(bars) - 1
        matches: list[NotificationMatch] = []
        fixed_window = bars[-HISTORY_BARS:]
        offset = len(bars) - len(fixed_window)
        fixed_results = [
            _shift_result(result, offset)
            for result in self.detector.detect(fixed_window)
        ]
        extended_results = (
            self.extended_detector.detect(bars)
            if timeframe in _PATTERN_009_TIMEFRAMES
            else ()
        )
        for result in (*fixed_results, *extended_results):
            if (
                result.pattern_id == "PATTERN_009"
                and timeframe not in _PATTERN_009_TIMEFRAMES
            ):
                continue
            if not result.detected or not _uses_right_edge(result, last_index):
                continue
            combination = self.priority_scorer.score(result, bars)
            matches.append(
                NotificationMatch(
                    symbol=symbol,
                    timeframe=timeframe,
                    detected_timestamp=bars[-1].timestamp,
                    pattern=result,
                    combination=combination,
                )
            )
        return sorted(matches, key=lambda item: item.pattern.pattern_id)


def _uses_right_edge(result: PatternResult, last_index: int) -> bool:
    """Require the latest closed candle to be a selected Pattern anchor."""

    geometry = result.geometry
    names = (
        ("upper_points", "lower_points")
        if result.pattern_id in {"PATTERN_002", "PATTERN_009"}
        else ("points",)
    )
    return any(
        index == last_index
        for name in names
        for index in _point_indexes(geometry.get(name, ()))
    )


def _point_indexes(raw: object) -> Iterable[int]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return
    for point in raw:
        if (
            isinstance(point, Sequence)
            and not isinstance(point, (str, bytes))
            and point
            and isinstance(point[0], (int, float))
        ):
            yield int(point[0])


def _shift_result(result: PatternResult, offset: int) -> PatternResult:
    """Map fixed-window geometry onto an extended 4h chart."""

    if offset == 0:
        return result
    geometry = dict(result.geometry)
    for name in (
        "points",
        "upper_points",
        "lower_points",
        "line_contacts",
        "neckline_points",
    ):
        if name in geometry:
            geometry[name] = _shift_points(geometry[name], offset)
    for name in ("line", "upper_line", "lower_line"):
        raw = geometry.get(name)
        if not isinstance(raw, dict):
            continue
        geometry[name] = {
            key: _shift_point(value, offset)
            for key, value in raw.items()
        }
    metadata = dict(result.metadata)
    for name in ("event_index", "detected_at_index"):
        value = metadata.get(name)
        if isinstance(value, int):
            metadata[name] = value + offset
    metadata["notification_window_start_index"] = offset
    return replace(result, geometry=geometry, metadata=metadata)


def _shift_points(raw: object, offset: int) -> object:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return raw
    return [_shift_point(point, offset) for point in raw]


def _shift_point(raw: object, offset: int) -> object:
    if (
        isinstance(raw, Sequence)
        and not isinstance(raw, (str, bytes))
        and len(raw) >= 2
        and isinstance(raw[0], (int, float))
    ):
        return (int(raw[0]) + offset, *raw[1:])
    return raw
