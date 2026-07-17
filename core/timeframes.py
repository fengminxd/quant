"""Canonical market-structure timeframe hierarchy.

Trading structures live on 15-minute, 1-hour, and 4-hour levels.  Daily bars
provide trend context only and must not be routed into trading-pattern scans.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil


MIN_STRUCTURE_SPAN_BARS = 40
MAX_STRUCTURE_SPAN_BARS = 160


class TimeframeRole(str, Enum):
    """Allowed use of a timeframe in the framework."""

    TRADING = "trading"
    TREND_CONTEXT = "trend_context"


class StructureSpanStatus(str, Enum):
    """Eligibility of a structure after timeframe normalization."""

    TRADING = "trading"
    BELOW_MINIMUM = "below_minimum"
    TREND_ONLY = "trend_only"


@dataclass(frozen=True)
class TimeframeLevel:
    """One ordered timeframe level and its permitted role."""

    name: str
    minutes: int
    role: TimeframeRole


@dataclass(frozen=True)
class StructureSpanResolution:
    """Normalized ownership of a bar span in the timeframe hierarchy."""

    source_timeframe: str
    timeframe: str
    span_bars: int
    status: StructureSpanStatus
    promotions: int = 0

    @property
    def is_tradable(self) -> bool:
        """Return whether the normalized structure may drive trading logic."""

        return self.status is StructureSpanStatus.TRADING


TRADING_TIMEFRAME_LEVELS = (
    TimeframeLevel("15m", 15, TimeframeRole.TRADING),
    TimeframeLevel("1h", 60, TimeframeRole.TRADING),
    TimeframeLevel("4h", 240, TimeframeRole.TRADING),
)
DAILY_TREND_LEVEL = TimeframeLevel("1d", 1_440, TimeframeRole.TREND_CONTEXT)
TIMEFRAME_LEVELS = TRADING_TIMEFRAME_LEVELS + (DAILY_TREND_LEVEL,)
TRADING_TIMEFRAMES = tuple(level.name for level in TRADING_TIMEFRAME_LEVELS)
TREND_TIMEFRAMES = (DAILY_TREND_LEVEL.name,)

_LEVEL_BY_NAME = {level.name: level for level in TIMEFRAME_LEVELS}
_LEVEL_INDEX = {level.name: index for index, level in enumerate(TIMEFRAME_LEVELS)}


def timeframe_level(timeframe: str) -> TimeframeLevel:
    """Return a configured level or reject unsupported timeframe aliases."""

    try:
        return _LEVEL_BY_NAME[timeframe]
    except KeyError as error:
        supported = ", ".join(_LEVEL_BY_NAME)
        message = f"unsupported framework timeframe: {timeframe}; expected {supported}"
        raise ValueError(message) from error


def resolve_structure_span(timeframe: str, span_bars: int) -> StructureSpanResolution:
    """Resolve which level owns a structure without making daily tradable.

    A span is measured in complete bar intervals.  Values above 160 are
    converted by elapsed time and promoted through 15m -> 1h -> 4h.  Promotion
    beyond 4h terminates at the daily trend-only context.
    """

    if isinstance(span_bars, bool) or not isinstance(span_bars, int) or span_bars < 0:
        raise ValueError("span_bars must be a non-negative integer")

    source = timeframe_level(timeframe)
    if source.role is TimeframeRole.TREND_CONTEXT:
        return StructureSpanResolution(
            timeframe,
            source.name,
            span_bars,
            StructureSpanStatus.TREND_ONLY,
        )
    if span_bars < MIN_STRUCTURE_SPAN_BARS:
        return StructureSpanResolution(
            timeframe,
            source.name,
            span_bars,
            StructureSpanStatus.BELOW_MINIMUM,
        )

    current = source
    normalized_span = span_bars
    promotions = 0
    while normalized_span > MAX_STRUCTURE_SPAN_BARS:
        next_level = TIMEFRAME_LEVELS[_LEVEL_INDEX[current.name] + 1]
        normalized_span = ceil(normalized_span * current.minutes / next_level.minutes)
        promotions += 1
        current = next_level
        if current.role is TimeframeRole.TREND_CONTEXT:
            return StructureSpanResolution(
                timeframe,
                current.name,
                normalized_span,
                StructureSpanStatus.TREND_ONLY,
                promotions,
            )

    return StructureSpanResolution(
        timeframe,
        current.name,
        normalized_span,
        StructureSpanStatus.TRADING,
        promotions,
    )
