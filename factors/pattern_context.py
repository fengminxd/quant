"""Pattern-gated selection and aggregation of context factors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.base import Factor, Pattern
from core.models import Bar, FactorResult, PatternResult
from factors.context_factors import (
    DowntrendStructureScore,
    EMA99ContextScore,
    HammerScore,
    InvertedHammerScore,
    PriorHighBreakoutScore,
    PriorLowBreakdownScore,
    UptrendStructureScore,
)
from features.basic import clamp
from features.context import ContextFeatureExtractor


@dataclass(frozen=True)
class FactorSpec:
    """One selected factor weight and its polarity for a pattern hypothesis."""

    name: str
    weight: float
    polarity: int = 1

    def __post_init__(self) -> None:
        if self.weight <= 0.0:
            raise ValueError("factor weight must be positive")
        if self.polarity not in {-1, 1}:
            raise ValueError("factor polarity must be -1 or 1")


@dataclass(frozen=True)
class PatternFactorProfile:
    """Configured context-factor selection for one pattern."""

    pattern_id: str
    direction: str
    pattern_weight: float
    factors: tuple[FactorSpec, ...]

    def __post_init__(self) -> None:
        total = self.pattern_weight + sum(spec.weight for spec in self.factors)
        if self.pattern_weight <= 0.0 or abs(total - 1.0) > 1e-9:
            raise ValueError("profile weights must be positive and sum to 1")


@dataclass(frozen=True)
class PatternContextEvaluation:
    """Detected pattern, selected factor evidence, and composite score."""

    pattern: PatternResult
    factors: Mapping[str, FactorResult]
    composite: FactorResult


class PatternContextScorer:
    """Apply context factors only after a configured pattern is detected."""

    def __init__(
        self,
        extractor: ContextFeatureExtractor | None = None,
        profiles: Mapping[str, PatternFactorProfile] | None = None,
        factors: Mapping[str, Factor] | None = None,
    ) -> None:
        self.extractor = extractor or ContextFeatureExtractor()
        self.profiles = dict(profiles or DEFAULT_PATTERN_FACTOR_PROFILES)
        self.factors = dict(factors or _default_factors())
        self._validate_configuration()

    def evaluate(
        self,
        pattern: Pattern,
        data: Sequence[Bar],
        as_of_index: int | None = None,
    ) -> PatternContextEvaluation:
        """Safely detect and score using bars no later than ``as_of_index``."""

        window, index = _window(data, as_of_index)
        result = pattern.detect(window)
        return self.score(result, window, index)

    def score(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        as_of_index: int | None = None,
    ) -> PatternContextEvaluation:
        """Score an already detected pattern against the supplied visible bars."""

        window, index = _window(data, as_of_index)
        if not pattern.detected:
            composite = FactorResult(
                "PatternConditionedCompositeScore",
                0.0,
                {"pattern_quality": pattern.score},
                {
                    "gate_passed": False,
                    "pattern_id": pattern.pattern_id,
                    "as_of_index": index,
                    "selected_factors": (),
                    "active_factors": (),
                },
            )
            return PatternContextEvaluation(pattern, {}, composite)
        if pattern.pattern_id not in self.profiles:
            raise ValueError(f"no context-factor profile for {pattern.pattern_id}")
        self._validate_as_of(pattern, index)
        profile = self.profiles[pattern.pattern_id]
        features = self.extractor.extract(window)
        results = {
            spec.name: self.factors[spec.name].calculate(features)
            for spec in profile.factors
        }
        effective: dict[str, float] = {}
        weighted_score = profile.pattern_weight * clamp(pattern.score)
        confidence = profile.pattern_weight
        active: list[str] = []
        for spec in profile.factors:
            result = results[spec.name]
            is_active = bool(result.metadata.get("active", False))
            raw_score = result.score if is_active else 50.0
            oriented_score = raw_score if spec.polarity > 0 else 100.0 - raw_score
            effective[spec.name] = round(oriented_score, 4)
            weighted_score += spec.weight * oriented_score
            factor_confidence = float(result.metadata.get("confidence", 0.0))
            confidence += spec.weight * clamp(factor_confidence, 0.0, 1.0)
            if is_active:
                active.append(spec.name)
        raw_scores = {name: result.score for name, result in results.items()}
        raw_scores["pattern_quality"] = pattern.score
        composite = FactorResult(
            f"{pattern.name} Context Composite Score",
            round(clamp(weighted_score), 4),
            raw_scores,
            {
                "gate_passed": True,
                "pattern_id": pattern.pattern_id,
                "direction": profile.direction,
                "as_of_index": index,
                "pattern_weight": profile.pattern_weight,
                "selected_factors": tuple(spec.name for spec in profile.factors),
                "active_factors": tuple(active),
                "weights": {spec.name: spec.weight for spec in profile.factors},
                "polarities": {spec.name: spec.polarity for spec in profile.factors},
                "effective_scores": effective,
                "confidence": round(clamp(confidence, 0.0, 1.0), 4),
                "inactive_policy": "neutral_50",
            },
        )
        return PatternContextEvaluation(pattern, results, composite)

    def score_detected(
        self, results: Sequence[PatternResult], data: Sequence[Bar]
    ) -> list[PatternContextEvaluation]:
        """Score only detected results that have configured factor profiles."""

        return [
            self.score(result, data)
            for result in results
            if result.detected and result.pattern_id in self.profiles
        ]

    def _validate_configuration(self) -> None:
        missing = {
            spec.name
            for profile in self.profiles.values()
            for spec in profile.factors
            if spec.name not in self.factors
        }
        if missing:
            raise ValueError(f"missing context factors: {sorted(missing)}")

    @staticmethod
    def _validate_as_of(pattern: PatternResult, as_of_index: int) -> None:
        detected_at = pattern.metadata.get("detected_at_index")
        if isinstance(detected_at, int) and detected_at > as_of_index:
            raise ValueError("as_of_index precedes pattern confirmation")
        points = pattern.geometry.get("points", ())
        point_indexes = [point[0] for point in points if isinstance(point, (list, tuple))]
        if point_indexes and max(point_indexes) > as_of_index:
            raise ValueError("as_of_index precedes pattern anchors")


def _window(
    data: Sequence[Bar], as_of_index: int | None
) -> tuple[Sequence[Bar], int]:
    if not data:
        raise ValueError("at least one bar is required")
    index = len(data) - 1 if as_of_index is None else as_of_index
    if index < 0 or index >= len(data):
        raise ValueError("as_of_index is outside supplied data")
    return data[: index + 1], index


def _default_factors() -> Mapping[str, Factor]:
    instances: tuple[Factor, ...] = (
        UptrendStructureScore(),
        DowntrendStructureScore(),
        EMA99ContextScore(),
        PriorHighBreakoutScore(),
        PriorLowBreakdownScore(),
        HammerScore(),
        InvertedHammerScore(),
    )
    return {type(instance).__name__: instance for instance in instances}


def _profile(
    pattern_id: str, direction: str, *, include_both_wicks: bool = False
) -> PatternFactorProfile:
    bullish = direction == "bullish"
    factors = [
        FactorSpec("UptrendStructureScore", 0.10, 1 if bullish else -1),
        FactorSpec("DowntrendStructureScore", 0.10, -1 if bullish else 1),
        FactorSpec("EMA99ContextScore", 0.10, 1 if bullish else -1),
        FactorSpec("PriorHighBreakoutScore", 0.15, 1 if bullish else -1),
        FactorSpec("PriorLowBreakdownScore", 0.15, -1 if bullish else 1),
    ]
    if include_both_wicks:
        factors.extend(
            [FactorSpec("HammerScore", 0.05), FactorSpec("InvertedHammerScore", 0.05)]
        )
        pattern_weight = 0.30
    else:
        wick = "HammerScore" if bullish else "InvertedHammerScore"
        factors.append(FactorSpec(wick, 0.05))
        pattern_weight = 0.35
    return PatternFactorProfile(pattern_id, direction, pattern_weight, tuple(factors))


DEFAULT_PATTERN_FACTOR_PROFILES: Mapping[str, PatternFactorProfile] = {
    "PATTERN_003": _profile("PATTERN_003", "bullish"),
    "PATTERN_004": _profile("PATTERN_004", "bullish"),
    "PATTERN_005": _profile("PATTERN_005", "bearish"),
    "PATTERN_006": _profile("PATTERN_006", "bearish"),
    "PATTERN_007": _profile("PATTERN_007", "bullish", include_both_wicks=True),
    "PATTERN_008": _profile("PATTERN_008", "bearish", include_both_wicks=True),
}
