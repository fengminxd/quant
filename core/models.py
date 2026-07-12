"""Shared data structures defined by API.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Bar:
    """Single OHLCV candle."""

    timestamp: int | str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str | None = None

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("bar.high must be greater than or equal to open/close/low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("bar.low must be less than or equal to open/close/high")
        if self.volume < 0:
            raise ValueError("bar.volume must be non-negative")


OHLCVSeries = Sequence[Bar]


@dataclass(frozen=True)
class FeatureResult:
    """Reusable feature value with a confidence estimate."""

    name: str
    value: float
    confidence: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactorResult:
    """Factor score in the 0-100 range."""

    name: str
    score: float
    features: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PatternResult:
    """Pattern detection result and extracted evidence."""

    pattern_id: str
    name: str
    detected: bool
    score: float
    features: Mapping[str, FeatureResult] = field(default_factory=dict)
    geometry: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class Signal(str, Enum):
    """Strategy-level signal placeholder."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"
