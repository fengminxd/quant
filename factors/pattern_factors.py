"""Factors mapping pattern features to 0-100 scores."""

from __future__ import annotations

from collections.abc import Mapping

from core.base import Factor
from core.models import FactorResult, FeatureResult
from features.basic import clamp


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].value if name in features else 0.0


class TrendlineSupportScore(Factor):
    """Score reliability of ascending trendline support."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Calculate score from touch, span, trend, volume, and fit quality."""

        touch_score = clamp(_value(features, "touch_count") / 5.0 * 100.0)
        span_score = clamp(_value(features, "line_span") / 20.0 * 100.0)
        volume_score = clamp(_value(features, "volume_ratio") * 50.0)
        fit_penalty = clamp(_value(features, "fit_error") * 100.0)
        score = clamp(
            0.30 * touch_score
            + 0.25 * span_score
            + 0.20 * _value(features, "trend_strength")
            + 0.15 * volume_score
            - 0.10 * fit_penalty
        )
        return FactorResult("TrendlineSupportScore", score, _feature_values(features))


class AscendingTriangleScore(Factor):
    """Score flat resistance plus rising demand compression."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Calculate ascending triangle factor score."""

        score = clamp(
            0.25 * _value(features, "resistance_flatness")
            + 0.25 * _value(features, "higher_low_score")
            + 0.20 * _value(features, "atr_compression")
            + 0.15 * _value(features, "volume_contraction")
            + 0.15 * _value(features, "breakout_strength")
        )
        return FactorResult("AscendingTriangleScore", score, _feature_values(features))


def _feature_values(features: Mapping[str, FeatureResult]) -> Mapping[str, float]:
    return {name: result.value for name, result in features.items()}
