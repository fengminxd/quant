"""Ascending Triangle pattern."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import AscendingTriangleScore
from features.basic import (
    atr_compression,
    breakout_strength,
    breakout_volume,
    higher_low_score,
    resistance_flatness,
    volume_contraction,
)
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector


class AscendingTriangle(Pattern):
    """Detect flat resistance with rising swing lows."""

    pattern_id = "PATTERN_002"
    name = "Ascending Triangle"

    def __init__(self, swing_detector: SwingDetector | None = None) -> None:
        self.swing_detector = swing_detector or SwingDetector(min_bars=3)
        self.factor = AscendingTriangleScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect ascending triangle from confirmed swings."""

        swings = self.swing_detector.detect(data)
        highs = [pivot for pivot in swings if pivot.kind == "high"][-4:]
        lows = [pivot for pivot in swings if pivot.kind == "low"][-4:]
        if len(highs) < 2 or len(lows) < 3:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        resistance = sum(pivot.price for pivot in highs) / len(highs)
        features = self._features(data, highs, lows, resistance)
        score = self.calculate_score(features)
        detected = score >= 50.0 and features["higher_low_score"].value >= 66.0
        detected = detected and features["resistance_flatness"].value > 0.0
        return PatternResult(
            self.pattern_id,
            self.name,
            detected,
            score,
            features,
            geometry={
                "resistance": resistance,
                "highs": [(p.index, p.price) for p in highs],
                "lows": [(p.index, p.price) for p in lows],
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features from the latest triangle candidate."""

        result = self.detect(data)
        return result.features

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Calculate score through the mapped factor."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable triangle geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _features(
        self,
        data: Sequence[Bar],
        highs: Sequence[Pivot],
        lows: Sequence[Pivot],
        resistance: float,
    ) -> Mapping[str, FeatureResult]:
        atr = average_true_range(data)[-1]
        return {
            "resistance_flatness": resistance_flatness(highs, atr),
            "higher_low_score": higher_low_score(lows),
            "atr_compression": atr_compression(data),
            "volume_contraction": volume_contraction(data),
            "breakout_strength": breakout_strength(data, resistance),
            "breakout_volume": breakout_volume(data),
        }
