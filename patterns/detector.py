"""Composable pattern detector registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from core.base import Pattern
from core.models import Bar, PatternResult
from core.timeframes import (
    MAX_STRUCTURE_SPAN_BARS,
    MIN_STRUCTURE_SPAN_BARS,
    TRADING_TIMEFRAMES,
    TimeframeRole,
    timeframe_level,
)


@dataclass(frozen=True)
class PatternPollResult:
    """A detected structure and the no-look-ahead window that produced it."""

    timeframe: str
    as_of_index: int
    window_start_index: int
    pattern: PatternResult


class PatternDetector:
    """Run multiple pattern detectors on the same OHLCV history."""

    def __init__(self, patterns: Iterable[Pattern] | None = None) -> None:
        self.patterns = list(patterns or [])

    def register(self, pattern: Pattern) -> None:
        """Register an additional pattern detector."""

        self.patterns.append(pattern)

    def detect(self, data: Sequence[Bar]) -> list[PatternResult]:
        """Detect all registered patterns."""

        return [pattern.detect(data) for pattern in self.patterns]

    def poll(
        self,
        data_by_timeframe: Mapping[str, Sequence[Bar]],
    ) -> list[PatternPollResult]:
        """Run one latest-candle polling pass over the three trading levels.

        Daily data is deliberately ignored here; it belongs to a separate HTF
        trend evaluation.  Calling this method after each closed candle creates
        the production polling behavior without exposing any future bar.
        """

        found: list[PatternPollResult] = []
        for timeframe in TRADING_TIMEFRAMES:
            data = data_by_timeframe.get(timeframe, ())
            if len(data) <= MIN_STRUCTURE_SPAN_BARS:
                continue
            found.extend(self.poll_at(data, timeframe, len(data) - 1))
        return found

    def poll_at(
        self,
        data: Sequence[Bar],
        timeframe: str,
        as_of_index: int,
    ) -> list[PatternPollResult]:
        """Evaluate one historical candle using only its visible trailing window."""

        level = timeframe_level(timeframe)
        if level.role is not TimeframeRole.TRADING:
            return []
        if as_of_index < 0 or as_of_index >= len(data):
            raise IndexError("as_of_index is outside the supplied candle sequence")
        if as_of_index < MIN_STRUCTURE_SPAN_BARS:
            return []
        self._validate_timeframe(data[: as_of_index + 1], timeframe)

        window_start = max(0, as_of_index - MAX_STRUCTURE_SPAN_BARS)
        window = data[window_start : as_of_index + 1]
        found: list[PatternPollResult] = []
        for result in self.detect(window):
            if not result.detected:
                continue
            structure_span = self._structure_span_bars(result)
            if structure_span is None or not (
                MIN_STRUCTURE_SPAN_BARS <= structure_span <= MAX_STRUCTURE_SPAN_BARS
            ):
                continue
            metadata = {
                **result.metadata,
                "timeframe_level": timeframe,
                "timeframe_role": level.role.value,
                "as_of_index": as_of_index,
                "window_start_index": window_start,
                "structure_span_bars": structure_span,
                "structure_min_span_bars": MIN_STRUCTURE_SPAN_BARS,
                "structure_max_span_bars": MAX_STRUCTURE_SPAN_BARS,
            }
            found.append(
                PatternPollResult(
                    timeframe,
                    as_of_index,
                    window_start,
                    replace(result, metadata=metadata),
                )
            )
        return found

    @staticmethod
    def _validate_timeframe(data: Sequence[Bar], timeframe: str) -> None:
        mismatched = next(
            (bar.timeframe for bar in data if bar.timeframe not in (None, timeframe)),
            None,
        )
        if mismatched is not None:
            raise ValueError(
                f"bar timeframe {mismatched!r} does not match polling level {timeframe!r}"
            )

    @staticmethod
    def _structure_span_bars(result: PatternResult) -> int | None:
        """Read the anchor span from the standard feature/geometry contracts."""

        metadata_span = result.metadata.get("structure_span_bars")
        if isinstance(metadata_span, (int, float)):
            return round(float(metadata_span))
        for name in ("span", "line_span"):
            feature = result.features.get(name)
            if feature is not None:
                return round(feature.value)

        indexes: list[int] = []
        for name in ("points", "upper_points", "lower_points"):
            points = result.geometry.get(name, ())
            if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
                continue
            indexes.extend(
                int(point[0])
                for point in points
                if isinstance(point, Sequence)
                and not isinstance(point, (str, bytes))
                and len(point) >= 1
                and isinstance(point[0], (int, float))
            )
        return max(indexes) - min(indexes) if indexes else None
