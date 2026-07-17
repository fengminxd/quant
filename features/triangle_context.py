"""Causal context features for directional triangle continuation hypotheses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.models import Bar, FeatureResult, PatternResult
from features.context import ContextFeatureExtractor
from features.ema_rejection import (
    upper_ema_wick_rejection_at_close,
    upper_ema_wick_rejection_indexes,
)
from indicators.atr import average_true_range
from indicators.ema import exponential_moving_average


def bearish_triangle_continuation_features(
    data: Sequence[Bar],
    pattern: PatternResult,
    *,
    ema_period: int = 99,
    trend_lookback: int = 20,
    decline_lookback_bars: int = 60,
) -> Mapping[str, FeatureResult]:
    """Describe prior downtrend and third-upper-anchor EMA rejection.

    Trend context is frozen at the first triangle anchor. EMA rejection is
    frozen at the third upper-boundary anchor, so later confirmation candles
    cannot change either observation.
    """

    if pattern.pattern_id != "PATTERN_002" or not pattern.detected:
        raise ValueError("a detected PATTERN_002 triangle is required")
    upper = _points(pattern, "upper_points")
    lower = _points(pattern, "lower_points")
    if len(upper) != 3:
        raise ValueError("bearish upper-anchor rejection requires three upper points")
    first_index = min(upper[0][0], lower[0][0])
    third_upper_index = upper[-1][0]
    if third_upper_index >= len(data):
        raise ValueError("triangle anchors are outside supplied data")

    prior = data[: first_index + 1]
    upper_window = data[: third_upper_index + 1]
    prior_features = ContextFeatureExtractor(
        ema_period=ema_period,
        trend_lookback=trend_lookback,
    ).extract(prior)
    prior_atr = max(average_true_range(prior)[-1], 1e-12)
    if decline_lookback_bars <= 0:
        raise ValueError("decline_lookback_bars must be positive")
    decline_lookback = min(first_index, decline_lookback_bars)
    decline_start = first_index - decline_lookback
    prior_decline = (
        (data[decline_start].high - data[first_index].close)
        / prior_atr
        if decline_lookback
        else 0.0
    )
    upper_bar = data[third_upper_index]
    atr = max(average_true_range(upper_window)[-1], 1e-12)
    ema = exponential_moving_average(upper_window, ema_period)[-1]
    body_top = max(upper_bar.open, upper_bar.close)
    rejection = upper_bar.high > ema and body_top < ema
    all_points = upper + lower
    span = max(point[0] for point in all_points) - min(
        point[0] for point in all_points
    )

    return {
        "prior_lower_high_ratio": _copy(prior_features, "lower_high_ratio"),
        "prior_lower_low_ratio": _copy(prior_features, "lower_low_ratio"),
        "prior_trend_efficiency_signed": _copy(
            prior_features, "trend_efficiency_signed"
        ),
        "prior_decline_atr": _feature(
            "prior_decline_atr",
            prior_decline,
            min(1.0, decline_lookback / decline_lookback_bars),
        ),
        "prior_decline_start_index": FeatureResult(
            "prior_decline_start_index",
            float(decline_start),
            1.0,
            {"timestamp": data[decline_start].timestamp},
        ),
        "prior_ema99_distance_atr": _copy(prior_features, "ema99_distance_atr"),
        "prior_ema99_slope_atr": _copy(prior_features, "ema99_slope_atr"),
        "prior_ema99_above_close_ratio": _copy(
            prior_features, "ema99_above_close_ratio"
        ),
        "upper_third_ema99_value": _feature(
            "upper_third_ema99_value", ema, min(1.0, len(upper_window) / ema_period)
        ),
        "upper_third_high_above_ema_atr": _feature(
            "upper_third_high_above_ema_atr", (upper_bar.high - ema) / atr
        ),
        "upper_third_body_below_ema_atr": _feature(
            "upper_third_body_below_ema_atr", (ema - body_top) / atr
        ),
        "upper_third_close_below_ema_atr": _feature(
            "upper_third_close_below_ema_atr", (ema - upper_bar.close) / atr
        ),
        "upper_third_ema_wick_rejection": _feature(
            "upper_third_ema_wick_rejection", 1.0 if rejection else 0.0
        ),
        "triangle_compression_ratio": _feature(
            "triangle_compression_ratio",
            pattern.features["convergence_ratio"].value,
        ),
        "triangle_structure_span": _feature("triangle_structure_span", float(span)),
        "triangle_quality_score": _feature("triangle_quality_score", pattern.score),
    }


def _points(pattern: PatternResult, name: str) -> tuple[tuple[int, float], ...]:
    raw = pattern.geometry.get(name)
    if not isinstance(raw, Sequence) or len(raw) not in {2, 3}:
        raise ValueError(f"triangle geometry requires two or three {name}")
    offset = pattern.metadata.get("window_start_index", 0)
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("window_start_index must be a non-negative integer")
    return tuple((int(point[0]) + offset, float(point[1])) for point in raw)


def _copy(features: Mapping[str, FeatureResult], name: str) -> FeatureResult:
    source = features[name]
    return FeatureResult(f"prior_{name}", source.value, source.confidence)


def _feature(name: str, value: float, confidence: float = 1.0) -> FeatureResult:
    return FeatureResult(name, float(value), float(confidence))
