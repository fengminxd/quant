"""Post-pattern context factors derived from price action and EMA99 context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Factor
from core.models import FactorResult, FeatureResult
from features.basic import clamp
from features.context import directional_structure_score


class UptrendStructureScore(Factor):
    """Score confirmed higher-high and higher-low market structure."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        score, sequence_confidence, active = directional_structure_score(
            features, bullish=True
        )
        return _result(
            "UptrendStructureScore", score, features, sequence_confidence,
            active=active,
            state="uptrend" if score >= 60.0 else "not_uptrend",
        )


class DowntrendStructureScore(Factor):
    """Score confirmed lower-high and lower-low market structure."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        score, sequence_confidence, active = directional_structure_score(
            features, bullish=False
        )
        return _result(
            "DowntrendStructureScore", score, features, sequence_confidence,
            active=active,
            state="downtrend" if score >= 60.0 else "not_downtrend",
        )


class EMA99ContextScore(Factor):
    """Score price acceptance above a rising EMA99 on a bullish 0-100 axis."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        confidence = _confidence(features, "ema99_value")
        distance_score = clamp(50.0 + _value(features, "ema99_distance_atr") * 25.0)
        slope_score = clamp(50.0 + _value(features, "ema99_slope_atr") * 15.0)
        persistence_score = clamp(_value(features, "ema99_above_close_ratio") * 100.0)
        score = 0.35 * distance_score + 0.35 * slope_score + 0.30 * persistence_score
        return _result(
            "EMA99ContextScore", score, features, confidence,
            active=confidence >= 1.0,
            state="bullish" if score > 55.0 else "bearish" if score < 45.0 else "neutral",
            extra={"axis": "bullish_high_bearish_low"},
        )


class PriorHighBreakoutScore(Factor):
    """Score close acceptance above the latest confirmed prior swing high."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        confidence = _confidence(features, "prior_swing_high")
        close_distance = _value(features, "breakout_close_distance_atr")
        high_distance = _value(features, "breakout_high_distance_atr")
        close_location = _value(features, "close_location")
        if confidence == 0.0:
            return _result("PriorHighBreakoutScore", 50.0, features, 0.0, False, "unavailable")
        if close_distance > 0.0:
            quality = (
                0.40 * clamp(close_distance * 100.0)
                + 0.30 * clamp(close_location * 100.0)
                + 0.30 * clamp(_value(features, "bullish_body_ratio") * 200.0)
            )
            return _result(
                "PriorHighBreakoutScore", 50.0 + 0.5 * quality, features,
                confidence, True, "breakout",
            )
        if high_distance > 0.0:
            rejection = clamp(high_distance * 40.0 + (1.0 - close_location) * 20.0)
            return _result(
                "PriorHighBreakoutScore", 50.0 - rejection, features,
                confidence, True, "false_breakout",
            )
        return _result("PriorHighBreakoutScore", 50.0, features, confidence, False, "below")


class PriorLowBreakdownScore(Factor):
    """Score close acceptance below the latest confirmed prior swing low."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        confidence = _confidence(features, "prior_swing_low")
        close_distance = _value(features, "breakdown_close_distance_atr")
        low_distance = _value(features, "breakdown_low_distance_atr")
        close_location = _value(features, "close_location")
        if confidence == 0.0:
            return _result("PriorLowBreakdownScore", 50.0, features, 0.0, False, "unavailable")
        if close_distance > 0.0:
            quality = (
                0.40 * clamp(close_distance * 100.0)
                + 0.30 * clamp((1.0 - close_location) * 100.0)
                + 0.30 * clamp(_value(features, "bearish_body_ratio") * 200.0)
            )
            return _result(
                "PriorLowBreakdownScore", 50.0 + 0.5 * quality, features,
                confidence, True, "breakdown",
            )
        if low_distance > 0.0:
            rejection = clamp(low_distance * 40.0 + close_location * 20.0)
            return _result(
                "PriorLowBreakdownScore", 50.0 - rejection, features,
                confidence, True, "false_breakdown",
            )
        return _result("PriorLowBreakdownScore", 50.0, features, confidence, False, "above")


class HammerScore(Factor):
    """Score lower-shadow rejection geometry on the latest closed candle."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        score, active, confidence = _wick_score(features, inverted=False)
        return _result(
            "HammerScore", score, features, confidence, active,
            "hammer" if active else "not_hammer",
        )


class InvertedHammerScore(Factor):
    """Score upper-shadow rejection geometry on the latest closed candle."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        score, active, confidence = _wick_score(features, inverted=True)
        return _result(
            "InvertedHammerScore", score, features, confidence, active,
            "inverted_hammer" if active else "not_inverted_hammer",
        )


def _wick_score(
    features: Mapping[str, FeatureResult], *, inverted: bool
) -> tuple[float, bool, float]:
    body = _value(features, "body_ratio")
    if inverted:
        dominant = _value(features, "upper_shadow_body_ratio")
        opposite = _value(features, "lower_shadow_ratio")
        body_location = _value(features, "body_top_location")
        location_score = clamp((0.45 - body_location) / 0.35 * 100.0)
        location_valid = body_location <= 0.40
    else:
        dominant = _value(features, "lower_shadow_body_ratio")
        opposite = _value(features, "upper_shadow_ratio")
        body_location = _value(features, "body_bottom_location")
        location_score = clamp((body_location - 0.55) / 0.35 * 100.0)
        location_valid = body_location >= 0.60
    score = (
        0.30 * clamp(dominant / 2.0 * 100.0)
        + 0.20 * clamp((0.40 - body) / 0.35 * 100.0)
        + 0.20 * clamp((0.15 - opposite) / 0.15 * 100.0)
        + 0.20 * location_score
        + 0.10 * clamp(_value(features, "range_atr_ratio") / 0.5 * 100.0)
    )
    confidence = _confidence(features, "body_ratio")
    active = (
        confidence > 0.0
        and 0.03 <= body <= 0.35
        and dominant >= 2.0
        and opposite <= 0.10
        and location_valid
    )
    return clamp(score), active, confidence


def _result(
    name: str,
    score: float,
    features: Mapping[str, FeatureResult],
    confidence: float,
    active: bool,
    state: str,
    extra: Mapping[str, object] | None = None,
) -> FactorResult:
    metadata: dict[str, object] = {
        "active": active,
        "confidence": clamp(confidence, 0.0, 1.0),
        "state": state,
    }
    metadata.update(extra or {})
    return FactorResult(name, round(clamp(score), 4), _values(features), metadata)


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].value if name in features else 0.0


def _confidence(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].confidence if name in features else 0.0


def _values(features: Mapping[str, FeatureResult]) -> Mapping[str, float]:
    return {name: result.value for name, result in features.items()}


CONTEXT_FACTORS: Sequence[type[Factor]] = (
    UptrendStructureScore,
    DowntrendStructureScore,
    EMA99ContextScore,
    PriorHighBreakoutScore,
    PriorLowBreakdownScore,
    HammerScore,
    InvertedHammerScore,
)
