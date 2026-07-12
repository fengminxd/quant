"""Deterministic price action features."""

from __future__ import annotations

import math
from collections.abc import Sequence

from core.models import Bar, FeatureResult
from indicators.atr import average_true_range
from indicators.swing import Pivot


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    """Clamp numeric scores to a bounded range."""

    return max(minimum, min(maximum, value))


def line_value(p1: Pivot, p2: Pivot, index: int) -> float:
    """Return y-value on the line through two pivots."""

    if p2.index == p1.index:
        return p1.price
    slope = (p2.price - p1.price) / (p2.index - p1.index)
    return p1.price + slope * (index - p1.index)


def trend_angle(points: Sequence[Pivot]) -> FeatureResult:
    """Trendline angle in degrees based on first and last point."""

    if len(points) < 2:
        return FeatureResult("line_angle", 0.0, 0.0)
    span = points[-1].index - points[0].index
    slope = 0.0 if span == 0 else (points[-1].price - points[0].price) / span
    return FeatureResult("line_angle", math.degrees(math.atan(slope)), 1.0)


def line_span(points: Sequence[Pivot]) -> FeatureResult:
    """Number of bars covered by a line."""

    if len(points) < 2:
        return FeatureResult("line_span", 0.0, 0.0)
    return FeatureResult("line_span", float(points[-1].index - points[0].index), 1.0)


def fit_error(points: Sequence[Pivot]) -> FeatureResult:
    """Mean absolute distance of points to the first-last trendline."""

    if len(points) < 2:
        return FeatureResult("fit_error", 0.0, 0.0)
    p1, p2 = points[0], points[-1]
    distances = [abs(point.price - line_value(p1, p2, point.index)) for point in points]
    return FeatureResult("fit_error", sum(distances) / len(distances), 1.0)


def atr_distance(data: Sequence[Bar], p1: Pivot, p2: Pivot) -> FeatureResult:
    """Latest close distance from line normalized by latest ATR."""

    if not data:
        return FeatureResult("atr_distance", 0.0, 0.0)
    atr = average_true_range(data)[-1]
    latest = len(data) - 1
    distance = abs(data[-1].close - line_value(p1, p2, latest))
    value = distance / atr if atr > 0 else 0.0
    return FeatureResult("atr_distance", value, 1.0 if atr > 0 else 0.0)


def break_count(data: Sequence[Bar], p1: Pivot, p2: Pivot) -> FeatureResult:
    """Count closes below a support line after the first pivot."""

    count = 0
    for index in range(p1.index + 1, len(data)):
        if data[index].close < line_value(p1, p2, index):
            count += 1
    return FeatureResult("break_count", float(count), 1.0)


def touch_count(points: Sequence[Pivot]) -> FeatureResult:
    """Number of swing touches used by a line."""

    return FeatureResult("touch_count", float(len(points)), 1.0 if points else 0.0)


def trend_strength(swings: Sequence[Pivot]) -> FeatureResult:
    """Score higher-high and higher-low structure from confirmed swings."""

    highs = [pivot for pivot in swings if pivot.kind == "high"]
    lows = [pivot for pivot in swings if pivot.kind == "low"]
    hh = sum(1 for a, b in zip(highs, highs[1:]) if b.price > a.price)
    hl = sum(1 for a, b in zip(lows, lows[1:]) if b.price > a.price)
    total = max(1, len(highs) - 1 + len(lows) - 1)
    return FeatureResult("trend_strength", clamp(100.0 * (hh + hl) / total), 1.0)


def volume_ratio(data: Sequence[Bar], period: int = 20) -> FeatureResult:
    """Latest volume divided by historical moving-average volume."""

    if not data:
        return FeatureResult("volume_ratio", 0.0, 0.0)
    window = data[-period:]
    average = sum(bar.volume for bar in window) / len(window)
    value = data[-1].volume / average if average > 0 else 0.0
    return FeatureResult("volume_ratio", value, 1.0 if average > 0 else 0.0)


def atr_compression(data: Sequence[Bar], period: int = 14, ma_period: int = 20) -> FeatureResult:
    """Score volatility contraction as ATR below its own average."""

    if len(data) < 2:
        return FeatureResult("atr_compression", 0.0, 0.0)
    atr_values = average_true_range(data, period)
    window = atr_values[-ma_period:]
    average = sum(window) / len(window)
    ratio = atr_values[-1] / average if average > 0 else 1.0
    return FeatureResult("atr_compression", clamp((1.5 - ratio) / 1.5 * 100.0), 1.0)


def breakout_strength(data: Sequence[Bar], resistance: float) -> FeatureResult:
    """Latest close expansion above resistance normalized by ATR."""

    if not data:
        return FeatureResult("breakout_strength", 0.0, 0.0)
    atr = average_true_range(data)[-1]
    value = max(0.0, data[-1].close - resistance) / atr if atr > 0 else 0.0
    return FeatureResult("breakout_strength", clamp(value * 100.0), 1.0 if atr > 0 else 0.0)


def resistance_flatness(highs: Sequence[Pivot], atr_value: float) -> FeatureResult:
    """Score how flat swing highs are relative to ATR."""

    if len(highs) < 2 or atr_value <= 0:
        return FeatureResult("resistance_flatness", 0.0, 0.0)
    prices = [pivot.price for pivot in highs]
    mean = sum(prices) / len(prices)
    variance = sum((price - mean) ** 2 for price in prices) / len(prices)
    normalized = math.sqrt(variance) / atr_value
    return FeatureResult("resistance_flatness", clamp((1.0 - normalized / 0.3) * 100.0), 1.0)


def higher_low_score(lows: Sequence[Pivot]) -> FeatureResult:
    """Score rising swing-low structure."""

    if len(lows) < 2:
        return FeatureResult("higher_low_score", 0.0, 0.0)
    rising = sum(1 for a, b in zip(lows, lows[1:]) if b.price > a.price)
    return FeatureResult("higher_low_score", clamp(100.0 * rising / (len(lows) - 1)), 1.0)


def volume_contraction(data: Sequence[Bar], lookback: int = 20) -> FeatureResult:
    """Score declining volume into consolidation."""

    if len(data) < 4:
        return FeatureResult("volume_contraction", 0.0, 0.0)
    window = data[-lookback:]
    midpoint = max(1, len(window) // 2)
    early = sum(bar.volume for bar in window[:midpoint]) / midpoint
    late = sum(bar.volume for bar in window[midpoint:]) / max(1, len(window) - midpoint)
    ratio = late / early if early > 0 else 1.0
    return FeatureResult("volume_contraction", clamp((1.2 - ratio) / 1.2 * 100.0), 1.0)


def breakout_volume(data: Sequence[Bar], period: int = 20) -> FeatureResult:
    """Score latest breakout volume against its moving average."""

    ratio = volume_ratio(data, period)
    return FeatureResult("breakout_volume", clamp((ratio.value - 1.0) * 100.0), ratio.confidence)
