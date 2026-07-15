"""Strict three-point trendline support pattern."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import ThreePointTrendlineSupportScore
from features.basic import fit_error, line_span, line_value, trend_angle
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector


@dataclass(frozen=True)
class ThreePointSupportCandidate:
    """Strict three-point support candidate."""

    points: tuple[Pivot, Pivot, Pivot]
    tolerance: float


class ThreePointTrendlineSupport(Pattern):
    """Strict support from exactly three rising swing lows."""

    pattern_id = "PATTERN_003"
    name = "Three Point Trendline Support"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_total_span: int = 40,
        min_leg_span: int = 10,
        atr_tolerance_ratio: float = 0.65,
    ) -> None:
        if min_total_span <= 0 or min_leg_span <= 0:
            raise ValueError("span constraints must be positive")
        if atr_tolerance_ratio < 0:
            raise ValueError("atr_tolerance_ratio must be non-negative")
        # Candidate spacing belongs to the trendline geometry rules below.  It
        # must not be reused as swing denoising, otherwise a valid pivot can be
        # discarded simply because the opposite turn happened quickly.
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.min_total_span = min_total_span
        self.min_leg_span = min_leg_span
        self.atr_tolerance_ratio = atr_tolerance_ratio
        self.factor = ThreePointTrendlineSupportScore(min_total_span)

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the highest-quality strict three-point support."""

        candidate = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features_for_candidate(data, candidate)
        score = self.calculate_score(features)
        points = candidate.points
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            score,
            features,
            geometry={
                "points": [(point.index, point.price) for point in points],
                "point_timestamps": [data[point.index].timestamp for point in points],
                "line": {
                    "start": (points[0].index, points[0].price),
                    "end": (points[2].index, points[2].price),
                },
            },
            metadata={
                "rule": "strict_three_point_slope_support",
                "timestamp_semantics": "bar_open_time",
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the best strict candidate."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features_for_candidate(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Calculate a 0-100 structural quality score."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable trendline geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(self, data: Sequence[Bar]) -> ThreePointSupportCandidate | None:
        # Only confirmed swing lows are eligible.  In particular, do not add
        # the last input candle as a synthetic boundary pivot: doing so would
        # recognize support before the right-side confirmation window exists.
        lows = self.swing_detector.lows(data)
        if len(lows) < 3:
            return None
        atr_values = average_true_range(data)
        atr = atr_values[-1] if atr_values else 0.0
        tolerance = max(1e-9, atr * self.atr_tolerance_ratio)
        candidates: list[ThreePointSupportCandidate] = []
        for combo in combinations(lows, 3):
            points = (combo[0], combo[1], combo[2])
            if self._is_valid_candidate(data, points, tolerance):
                candidates.append(ThreePointSupportCandidate(points, tolerance))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: self._rank(candidate))

    def _is_valid_candidate(
        self,
        data: Sequence[Bar],
        points: tuple[Pivot, Pivot, Pivot],
        tolerance: float,
    ) -> bool:
        p1, p2, p3 = points
        if not self._passes_geometry(points):
            return False
        if abs(p2.price - line_value(p1, p3, p2.index)) > tolerance:
            return False
        valid_contacts = [
            self._anchor_contact_is_valid(data[point.index], line_value(p1, p3, point.index), tolerance)
            for point in points
        ]
        if not all(valid_contacts):
            return False
        return self._body_violation_count(data, points) == 0

    def _features_for_candidate(
        self,
        data: Sequence[Bar],
        candidate: ThreePointSupportCandidate,
    ) -> Mapping[str, FeatureResult]:
        points = candidate.points
        p1, p3 = points[0], points[2]
        atr = average_true_range(data)[-1]
        slope = (p3.price - p1.price) / (p3.index - p1.index)
        error = fit_error(points).value
        return {
            "touch_count": FeatureResult("touch_count", 3.0, 1.0),
            "line_span": line_span(points),
            "leg_1_span": FeatureResult("leg_1_span", float(points[1].index - points[0].index), 1.0),
            "leg_2_span": FeatureResult("leg_2_span", float(points[2].index - points[1].index), 1.0),
            "line_slope": FeatureResult("line_slope", slope, 1.0),
            "line_angle": trend_angle(points),
            "fit_error": FeatureResult("fit_error", error, 1.0),
            "fit_error_atr": FeatureResult("fit_error_atr", error / atr if atr > 0 else 0.0, 1.0),
            "body_violation_count": FeatureResult(
                "body_violation_count",
                float(self._body_violation_count(data, points)),
                1.0,
            ),
            "tolerance": FeatureResult("tolerance", candidate.tolerance, 1.0),
        }

    def _passes_geometry(self, points: tuple[Pivot, Pivot, Pivot]) -> bool:
        p1, p2, p3 = points
        total_span = p3.index - p1.index
        leg_1_span = p2.index - p1.index
        leg_2_span = p3.index - p2.index
        return (
            p1.price < p2.price < p3.price
            and total_span >= self.min_total_span
            and leg_1_span >= self.min_leg_span
            and leg_2_span >= self.min_leg_span
        )

    @staticmethod
    def _anchor_contact_is_valid(bar: Bar, value: float, tolerance: float) -> bool:
        body_low = min(bar.open, bar.close)
        return bar.low - tolerance <= value <= body_low

    @staticmethod
    def _body_violation_count(data: Sequence[Bar], points: tuple[Pivot, Pivot, Pivot]) -> int:
        p1, p3 = points[0], points[2]
        anchor_indexes = {point.index for point in points}
        violations = 0
        for index in range(p1.index, p3.index + 1):
            if index in anchor_indexes:
                continue
            bar = data[index]
            value = line_value(p1, p3, index)
            body_low = min(bar.open, bar.close)
            body_high = max(bar.open, bar.close)
            if body_low <= value <= body_high:
                violations += 1
        return violations

    @staticmethod
    def _rank(candidate: ThreePointSupportCandidate) -> tuple[float, float]:
        points = candidate.points
        return (line_span(points).value, -fit_error(points).value)
