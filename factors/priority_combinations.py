"""Score and label the eight fixed high-priority pattern combinations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Factor
from core.models import Bar, FactorResult, FeatureResult, PatternResult
from features.priority_combinations import PriorityCombinationFeatureExtractor
from features.priority_profiles import PriorityCombinationFeatureSet


class PriorityFixedCombinationScore(Factor):
    """Score condition coverage after all fixed pattern/trend gates pass."""

    def __init__(self, feature_set: PriorityCombinationFeatureSet) -> None:
        self.feature_set = feature_set

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return 0-100 coverage and an explicit priority marker."""

        gate_names = ("pattern_gate", "timeframe_gate", "variant_gate", "trend_gate")
        gate_passed = all(features[name].value == 1.0 for name in gate_names)
        matched = tuple(
            name
            for name in self.feature_set.condition_names
            if features[name].confidence > 0.0 and features[name].value == 1.0
        )
        matched_count = len(matched)
        total = len(self.feature_set.condition_names)
        active = gate_passed and matched_count > 0
        score = 100.0 * matched_count / total if active else 0.0
        evidence = {
            name: dict(features[name].metadata)
            for name in self.feature_set.condition_names
        }
        level_sources = tuple(
            (int(item["source_index"]), float(item["level"]))
            for name, item in evidence.items()
            if name in matched
            and isinstance(item.get("source_index"), int)
            and int(item["source_index"]) >= 0
            and isinstance(item.get("level"), (int, float))
        )
        level_relations = tuple(
            (
                name,
                str(item["rule_type"]),
                int(item["source_index"]),
                int(item["target_index"]),
                float(item["level"]),
            )
            for name, item in evidence.items()
            if name in matched
            and isinstance(item.get("rule_type"), str)
            and isinstance(item.get("source_index"), int)
            and int(item["source_index"]) >= 0
            and isinstance(item.get("target_index"), int)
            and int(item["target_index"]) >= 0
            and isinstance(item.get("level"), (int, float))
        )
        gate_confidence = min(
            (features[name].confidence for name in gate_names), default=0.0
        )
        condition_confidence = sum(
            features[name].confidence for name in self.feature_set.condition_names
        ) / total
        confidence = min(gate_confidence, condition_confidence)
        return FactorResult(
            f"{self.feature_set.combination_id} Priority Fixed Combination Score",
            round(score, 4),
            {name: feature.value for name, feature in features.items()},
            {
                "active": active,
                "priority_fixed_combination": active,
                "combination_id": self.feature_set.combination_id,
                "combination_name": self.feature_set.name,
                "gate_passed": gate_passed,
                "matched_conditions": matched,
                "matched_count": matched_count,
                "condition_count": total,
                "combination_size": matched_count,
                "condition_evidence": evidence,
                "level_sources": level_sources,
                "level_relations": level_relations,
                "confidence": confidence,
                "score_semantics": "matched_condition_coverage",
                "signal_semantics": "score_and_label_only",
            },
        )


class PriorityCombinationScorer:
    """Evaluate fixed combinations against one detected pattern and visible history."""

    def __init__(
        self, extractor: PriorityCombinationFeatureExtractor | None = None
    ) -> None:
        self.extractor = extractor or PriorityCombinationFeatureExtractor()

    def score(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        *,
        as_of_index: int | None = None,
        window_start_index: int | None = None,
    ) -> FactorResult:
        """Score a configured combination without viewing bars after ``as_of_index``."""

        if not pattern.detected:
            return self._inactive(pattern, "pattern_not_detected")
        feature_set = self.extractor.extract(
            pattern,
            data,
            as_of_index=as_of_index,
            window_start_index=window_start_index,
        )
        if feature_set is None:
            return self._inactive(pattern, "combination_not_configured")
        return PriorityFixedCombinationScore(feature_set).calculate(
            feature_set.features
        )

    @staticmethod
    def _inactive(pattern: PatternResult, state: str) -> FactorResult:
        return FactorResult(
            "Priority Fixed Combination Score",
            0.0,
            {"pattern_quality": pattern.score},
            {
                "active": False,
                "priority_fixed_combination": False,
                "pattern_id": pattern.pattern_id,
                "state": state,
                "matched_conditions": (),
            },
        )
