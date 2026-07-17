"""Directional continuation scores for otherwise neutral triangle geometry."""

from __future__ import annotations

from collections.abc import Mapping

from core.base import Factor
from core.models import FactorResult, FeatureResult
from features.basic import clamp


class TriangleBearishContinuationScore(Factor):
    """Score a triangle as a possible pause inside an established decline."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return a 0-100 score without emitting a trading instruction."""

        bearish_efficiency = clamp(
            50.0 - _value(features, "prior_trend_efficiency_signed") * 50.0
        )
        structure = (
            0.35 * _value(features, "prior_lower_high_ratio") * 100.0
            + 0.20 * _value(features, "prior_lower_low_ratio") * 100.0
            + 0.30 * clamp(_value(features, "prior_decline_atr") * 25.0)
            + 0.15 * bearish_efficiency
        )
        ema_trend = (
            0.35 * clamp(-_value(features, "prior_ema99_distance_atr") * 35.0)
            + 0.35 * clamp(-_value(features, "prior_ema99_slope_atr") * 50.0)
            + 0.30
            * clamp(
                (1.0 - _value(features, "prior_ema99_above_close_ratio")) * 100.0
            )
        )
        rejection_present = _value(
            features, "upper_third_ema_wick_rejection"
        ) == 1.0
        rejection = _rejection_score(features) if rejection_present else 0.0
        compression = clamp(_value(features, "triangle_compression_ratio") * 200.0)
        score = clamp(
            0.25 * structure
            + 0.30 * ema_trend
            + 0.30 * rejection
            + 0.15 * compression
        )
        confidence = min(feature.confidence for feature in features.values())
        active = rejection_present and ema_trend >= 60.0 and score >= 60.0
        return FactorResult(
            "TriangleBearishContinuationScore",
            round(score, 4),
            {name: feature.value for name, feature in features.items()},
            {
                "active": active,
                "confidence": round(confidence, 4),
                "state": (
                    "bearish_continuation_entry_candidate"
                    if active
                    else "not_confirmed"
                ),
                "confirmation": "third_upper_ema_rejection",
                "downside_break_required": False,
                "component_scores": {
                    "prior_structure": round(structure, 4),
                    "prior_ema_trend": round(ema_trend, 4),
                    "upper_ema_rejection": round(rejection, 4),
                    "triangle_compression": round(compression, 4),
                },
            },
        )


def _rejection_score(features: Mapping[str, FeatureResult]) -> float:
    high_cross = clamp(_value(features, "upper_third_high_above_ema_atr") * 100.0)
    close_reject = clamp(_value(features, "upper_third_close_below_ema_atr") * 100.0)
    return 60.0 + 0.20 * high_cross + 0.20 * close_reject


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].value
