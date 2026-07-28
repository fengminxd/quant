"""Continuous score for causal structure-zone entries."""

from __future__ import annotations

from collections.abc import Mapping

from core.base import Factor
from core.models import FactorResult, FeatureResult
from features.basic import clamp


class EntryQualityScore(Factor):
    """Score proximity, retest, reclaim, and setup freshness."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return 0-100 without directly returning Buy or Sell."""

        gate = _value(features, "entry_gate_passed") == 1.0
        distance = _value(features, "entry_distance_atr")
        maximum = max(_value(features, "max_close_distance_atr"), 1e-12)
        proximity = clamp(100.0 * (1.0 - distance / maximum))
        retest = 100.0 * _value(features, "structure_retest")
        reclaim = 100.0 * _value(features, "structure_reclaimed")
        age = max(0.0, _value(features, "bars_since_detection"))
        wait = max(_value(features, "max_wait_bars"), 1.0)
        freshness = clamp(100.0 - age * (100.0 / wait))
        score = clamp(
            0.40 * proximity
            + 0.25 * retest
            + 0.20 * reclaim
            + 0.15 * freshness
        )
        confidence = min(
            (feature.confidence for feature in features.values()), default=0.0
        )
        return FactorResult(
            "EntryQualityScore",
            round(score, 4),
            {name: feature.value for name, feature in features.items()},
            {
                "active": gate,
                "state": "retest_reclaimed" if gate else "waiting_for_retest",
                "confidence": round(confidence, 4),
                "component_scores": {
                    "proximity": round(proximity, 4),
                    "retest": round(retest, 4),
                    "reclaim": round(reclaim, 4),
                    "freshness": round(freshness, 4),
                },
            },
        )


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    feature = features.get(name)
    return feature.value if feature is not None else 0.0
