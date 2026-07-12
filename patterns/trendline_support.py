"""Trendline Support pattern."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import TrendlineSupportScore
from features.basic import (
    atr_distance,
    break_count,
    fit_error,
    line_span,
    line_value,
    touch_count,
    trend_angle,
    trend_strength,
    volume_ratio,
)
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector


class TrendlineSupport(Pattern):
    """Detect support from at least three rising swing lows."""

    pattern_id = "PATTERN_001"
    name = "Trendline Support"

    def __init__(self, swing_detector: SwingDetector | None = None) -> None:
        self.swing_detector = swing_detector or SwingDetector(min_bars=5)
        self.factor = TrendlineSupportScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the highest-quality ascending support trendline."""

        candidate = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features_for_candidate(data, candidate)
        score = self.calculate_score(features)
        return PatternResult(
            self.pattern_id,
            self.name,
            score >= 50.0,
            score,
            features,
            geometry={"points": [(p.index, p.price) for p in candidate]},
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the best candidate trendline."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features_for_candidate(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Calculate score through the mapped factor."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable trendline geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(self, data: Sequence[Bar]) -> list[Pivot] | None:
        lows = self.swing_detector.lows(data)
        if len(lows) < 3:
            return None
        atr = average_true_range(data)[-1]
        valid: list[list[Pivot]] = []
        for combo in combinations(lows, 3):
            points = list(combo)
            if not self._is_valid_geometry(points):
                continue
            error = fit_error(points).value
            if atr > 0 and error <= 0.5 * atr:
                valid.append(self._extend_touches(lows, points, atr))
        if not valid:
            return None
        return max(valid, key=lambda points: self._candidate_rank(data, points))

    def _features_for_candidate(
        self, data: Sequence[Bar], points: Sequence[Pivot]
    ) -> Mapping[str, FeatureResult]:
        swings = self.swing_detector.detect(data)
        p1, p2 = points[0], points[-1]
        return {
            "touch_count": touch_count(points),
            "line_span": line_span(points),
            "line_angle": trend_angle(points),
            "fit_error": fit_error(points),
            "atr_distance": atr_distance(data, p1, p2),
            "break_count": break_count(data, p1, p2),
            "trend_strength": trend_strength(swings),
            "volume_ratio": volume_ratio(data),
        }

    @staticmethod
    def _is_valid_geometry(points: Sequence[Pivot]) -> bool:
        prices_rise = points[0].price < points[1].price < points[2].price
        spacing_ok = points[1].index - points[0].index >= 5
        spacing_ok = spacing_ok and points[2].index - points[1].index >= 5
        return prices_rise and spacing_ok

    @staticmethod
    def _extend_touches(lows: Sequence[Pivot], points: Sequence[Pivot], atr: float) -> list[Pivot]:
        p1, p2 = points[0], points[-1]
        tolerance = 0.5 * atr
        touched = [
            low
            for low in lows
            if p1.index <= low.index <= p2.index
            and abs(low.price - line_value(p1, p2, low.index)) <= tolerance
        ]
        return sorted(set(touched + list(points)), key=lambda pivot: pivot.index)

    @staticmethod
    def _candidate_rank(data: Sequence[Bar], points: Sequence[Pivot]) -> tuple[float, ...]:
        span = line_span(points).value
        touches = touch_count(points).value
        error = fit_error(points).value
        breaks = break_count(data, points[0], points[-1]).value
        return (span, touches, -error, -breaks)
