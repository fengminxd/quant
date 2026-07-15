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


class TriangleScore(Factor):
    """Score fitted inward boundaries and volatility/volume compression."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Calculate a direction-neutral converging-triangle score."""

        score = clamp(
            0.20 * _value(features, "boundary_direction_score")
            + 0.20 * _value(features, "boundary_fit_score")
            + 0.20 * _value(features, "convergence_score")
            + 0.15 * _value(features, "atr_compression")
            + 0.10 * _value(features, "volume_contraction")
            + 0.15 * _value(features, "breakout_strength")
        )
        return FactorResult("TriangleScore", round(score, 4), _feature_values(features))


AscendingTriangleScore = TriangleScore


class ThreePointTrendlineSupportScore(Factor):
    """Score the structural quality of strict ascending support."""

    def __init__(self, min_total_span: int = 40) -> None:
        if min_total_span <= 0:
            raise ValueError("min_total_span must be positive")
        self.min_total_span = min_total_span

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return a 0-100 score without emitting a trading direction."""

        span_score = clamp(
            _value(features, "line_span") / self.min_total_span * 100.0
        )
        fit_score = clamp(100.0 - _value(features, "fit_error_atr") * 100.0)
        slope_score = 100.0 if _value(features, "line_slope") > 0.0 else 0.0
        body_score = (
            100.0 if _value(features, "body_violation_count") == 0.0 else 0.0
        )
        score = clamp(
            0.25 * span_score
            + 0.25 * fit_score
            + 0.25 * slope_score
            + 0.25 * body_score
        )
        return FactorResult(
            "ThreePointTrendlineSupportScore",
            round(score, 4),
            _feature_values(features),
        )


class ThreePointTrendlineResistanceScore(Factor):
    """Score the structural quality of strict descending resistance."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return a 0-100 score without emitting a trading direction."""

        span_score = clamp(_value(features, "line_span") / 40.0 * 100.0)
        fit_score = clamp(100.0 - _value(features, "fit_error_atr") * 100.0)
        slope_score = 100.0 if _value(features, "line_slope") < 0.0 else 0.0
        body_score = 100.0 if _value(features, "body_violation_count") == 0.0 else 0.0
        wick_score = clamp(_value(features, "upper_shadow_cross_count") / 6.0 * 100.0)
        score = clamp(
            0.25 * span_score
            + 0.25 * fit_score
            + 0.20 * slope_score
            + 0.20 * body_score
            + 0.10 * wick_score
        )
        return FactorResult(
            "ThreePointTrendlineResistanceScore",
            round(score, 4),
            _feature_values(features),
        )


class HorizontalResistanceScore(Factor):
    """Score a two-anchor horizontal resistance without trading direction."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Map span, alignment, and intervening-price containment to 0-100."""

        span_score = clamp(_value(features, "span") / 40.0 * 100.0)
        alignment_score = clamp(
            100.0 - _value(features, "anchor_overshoot_atr") * 50.0
        )
        clearance_score = clamp(
            50.0 + _value(features, "intermediate_clearance_atr") * 50.0
        )
        open_margin_score = clamp(
            50.0 + _value(features, "intermediate_open_margin_atr") * 50.0
        )
        if _value(features, "penetration_count") > 0.0:
            clearance_score = 0.0
        if _value(features, "open_violation_count") > 0.0:
            open_margin_score = 0.0
        score = clamp(
            0.30 * span_score
            + 0.30 * alignment_score
            + 0.25 * clearance_score
            + 0.15 * open_margin_score
        )
        return FactorResult(
            "HorizontalResistanceScore",
            round(score, 4),
            _feature_values(features),
        )


class InverseHeadShouldersScore(Factor):
    """Score inverse-head-and-shoulders structure and neckline confirmation."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return a bounded quality score without emitting a trade direction."""

        score = _head_shoulders_quality(
            features,
            head_key="head_depth_atr",
            prior_key="prior_decline_atr",
            confirmation_key="breakout_confirmed",
            distance_key="breakout_distance_atr",
            volume_key="breakout_volume_ratio",
        )
        return FactorResult(
            "InverseHeadShouldersScore",
            round(score, 4),
            _feature_values(features),
        )


class HeadAndShouldersTopScore(Factor):
    """Score head-and-shoulders top structure and neckline breakdown."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return a bounded quality score without emitting a trade direction."""

        score = _head_shoulders_quality(
            features,
            head_key="head_height_atr",
            prior_key="prior_advance_atr",
            confirmation_key="breakdown_confirmed",
            distance_key="breakdown_distance_atr",
            volume_key="breakdown_volume_ratio",
        )
        return FactorResult(
            "HeadAndShouldersTopScore",
            round(score, 4),
            _feature_values(features),
        )


def _head_shoulders_quality(
    features: Mapping[str, FeatureResult],
    *,
    head_key: str,
    prior_key: str,
    confirmation_key: str,
    distance_key: str,
    volume_key: str,
) -> float:
    """Score mirrored head-and-shoulders features through one shared formula."""

    span_score = clamp(_value(features, "span") / 40.0 * 100.0)
    shoulder_score = clamp(
        (1.0 - _value(features, "shoulder_price_error_atr")) * 100.0
    )
    height_score = clamp(_value(features, head_key) / 1.5 * 100.0)
    extreme_score = clamp(
        (0.1 - _value(features, "head_extreme_error_atr")) / 0.1 * 100.0
    )
    head_score = 0.8 * height_score + 0.2 * extreme_score
    duration_score = clamp((1.0 - _value(features, "duration_asymmetry")) * 100.0)
    prior_score = clamp(_value(features, prior_key) / 3.0 * 100.0)
    confirmation_score = 0.0
    if _value(features, confirmation_key) > 0.0:
        distance_score = clamp(_value(features, distance_key) * 100.0)
        volume_score = clamp((_value(features, volume_key) - 1.0) * 100.0)
        confirmation_score = 60.0 + 0.25 * distance_score + 0.15 * volume_score
    return clamp(
        0.20 * span_score
        + 0.25 * shoulder_score
        + 0.20 * head_score
        + 0.15 * duration_score
        + 0.05 * prior_score
        + 0.15 * confirmation_score
    )


def _feature_values(features: Mapping[str, FeatureResult]) -> Mapping[str, float]:
    return {name: result.value for name, result in features.items()}
