"""Core API contracts for the price action framework."""

from core.base import Factor, Feature, Pattern, Strategy
from core.models import (
    Bar,
    FactorResult,
    FeatureResult,
    OHLCVSeries,
    PatternResult,
    Signal,
)
from core.timeframes import (
    DAILY_TREND_LEVEL,
    MAX_STRUCTURE_SPAN_BARS,
    MIN_STRUCTURE_SPAN_BARS,
    TIMEFRAME_LEVELS,
    TRADING_TIMEFRAME_LEVELS,
    TRADING_TIMEFRAMES,
    TREND_TIMEFRAMES,
    StructureSpanResolution,
    StructureSpanStatus,
    TimeframeLevel,
    TimeframeRole,
    resolve_structure_span,
    timeframe_level,
)

__all__ = [
    "Bar",
    "Factor",
    "FactorResult",
    "Feature",
    "FeatureResult",
    "OHLCVSeries",
    "Pattern",
    "PatternResult",
    "Signal",
    "Strategy",
    "DAILY_TREND_LEVEL",
    "MAX_STRUCTURE_SPAN_BARS",
    "MIN_STRUCTURE_SPAN_BARS",
    "StructureSpanResolution",
    "StructureSpanStatus",
    "TIMEFRAME_LEVELS",
    "TRADING_TIMEFRAME_LEVELS",
    "TRADING_TIMEFRAMES",
    "TREND_TIMEFRAMES",
    "TimeframeLevel",
    "TimeframeRole",
    "resolve_structure_span",
    "timeframe_level",
]
