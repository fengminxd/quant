"""Strict three-point descending trendline resistance pattern."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import ThreePointTrendlineResistanceScore
from features.basic import fit_error, line_span, line_value, trend_angle
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector


@dataclass(frozen=True)
class ThreePointResistanceCandidate:
    """Three swing-high candles supporting one descending resistance line."""

    points: tuple[Pivot, Pivot, Pivot]
    tolerance: float
    line_contacts: tuple[Pivot, ...]
    valid_triplet_count: int = 1


class ThreePointTrendlineResistance(Pattern):
    """Detect strict resistance from three descending swing-high candles.

    Candle timestamps are interpreted as opening timestamps. The detector is
    timeframe agnostic: span constraints are measured in complete input bars.
    """

    pattern_id = "PATTERN_005"
    name = "Three Point Trendline Resistance"

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
        self.swing_detector = swing_detector or SwingDetector(min_bars=min_leg_span)
        self.min_total_span = min_total_span
        self.min_leg_span = min_leg_span
        self.atr_tolerance_ratio = atr_tolerance_ratio
        self.factor = ThreePointTrendlineResistanceScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the highest-ranked valid descending resistance line."""

        candidate = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features_for_candidate(data, candidate)
        points = candidate.points
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            self.calculate_score(features),
            features,
            geometry={
                "points": [(point.index, point.price) for point in points],
                "point_timestamps": [data[point.index].timestamp for point in points],
                "line_contacts": [
                    (point.index, point.price) for point in candidate.line_contacts
                ],
                "line": {
                    "start": (points[0].index, points[0].price),
                    "end": (points[2].index, points[2].price),
                },
            },
            metadata={
                "rule": "strict_three_point_descending_resistance",
                "timestamp_semantics": "bar_open_time",
                "valid_triplet_count": candidate.valid_triplet_count,
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the highest-ranked valid line."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features_for_candidate(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Map structural features to a 0-100 factor score."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable resistance geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(self, data: Sequence[Bar]) -> ThreePointResistanceCandidate | None:
        highs = self.swing_detector.highs(data)
        if len(highs) < 3:
            return None
        atr_values = average_true_range(data)
        atr = atr_values[-1] if atr_values else 0.0
        tolerance = max(1e-9, atr * self.atr_tolerance_ratio)
        valid_points = [
            points
            for combo in combinations(highs, 3)
            if self._is_valid_candidate(data, points := (combo[0], combo[1], combo[2]), tolerance)
        ]
        if not valid_points:
            return None
        points = max(valid_points, key=self._rank)
        contacts = tuple(self._line_contacts(data, highs, points, tolerance))
        return ThreePointResistanceCandidate(points, tolerance, contacts, len(valid_points))

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
        if not all(
            self._anchor_contact_is_valid(
                data[point.index], line_value(p1, p3, point.index)
            )
            for point in points
        ):
            return False
        return self._body_violation_count(data, points) == 0

    def _features_for_candidate(
        self,
        data: Sequence[Bar],
        candidate: ThreePointResistanceCandidate,
    ) -> Mapping[str, FeatureResult]:
        points = candidate.points
        p1, p3 = points[0], points[2]
        atr_values = average_true_range(data)
        atr = atr_values[-1] if atr_values else 0.0
        error = fit_error(points).value
        slope = (p3.price - p1.price) / (p3.index - p1.index)
        return {
            "anchor_count": FeatureResult("anchor_count", 3.0, 1.0),
            "touch_count": FeatureResult("touch_count", float(len(candidate.line_contacts)), 1.0),
            "line_span": line_span(points),
            "leg_1_span": FeatureResult("leg_1_span", float(points[1].index - p1.index), 1.0),
            "leg_2_span": FeatureResult("leg_2_span", float(p3.index - points[1].index), 1.0),
            "line_slope": FeatureResult("line_slope", slope, 1.0),
            "line_angle": trend_angle(points),
            "fit_error": FeatureResult("fit_error", error, 1.0),
            "fit_error_atr": FeatureResult("fit_error_atr", error / atr if atr > 0 else 0.0, 1.0),
            "body_violation_count": FeatureResult(
                "body_violation_count", float(self._body_violation_count(data, points)), 1.0
            ),
            "upper_shadow_cross_count": FeatureResult(
                "upper_shadow_cross_count", float(self._upper_shadow_cross_count(data, points)), 1.0
            ),
            "open_touch_count": FeatureResult(
                "open_touch_count", float(self._open_touch_count(data, points)), 1.0
            ),
            "valid_triplet_count": FeatureResult(
                "valid_triplet_count", float(candidate.valid_triplet_count), 1.0
            ),
            "tolerance": FeatureResult("tolerance", candidate.tolerance, 1.0),
        }

    def _passes_geometry(self, points: tuple[Pivot, Pivot, Pivot]) -> bool:
        p1, p2, p3 = points
        return (
            p1.price > p2.price > p3.price
            and p3.index - p1.index >= self.min_total_span
            and p2.index - p1.index >= self.min_leg_span
            and p3.index - p2.index >= self.min_leg_span
        )

    @staticmethod
    def _anchor_contact_is_valid(bar: Bar, value: float) -> bool:
        body_high = max(bar.open, bar.close)
        in_upper_shadow = body_high <= value <= bar.high
        touches_open = math.isclose(value, bar.open, rel_tol=1e-9, abs_tol=1e-9)
        return in_upper_shadow or touches_open

    @staticmethod
    def _body_violation_count(data: Sequence[Bar], points: tuple[Pivot, Pivot, Pivot]) -> int:
        p1, p3 = points[0], points[2]
        anchors = {point.index for point in points}
        violations = 0
        for index in range(p1.index, p3.index + 1):
            if index in anchors:
                continue
            value = line_value(p1, p3, index)
            body_low = min(data[index].open, data[index].close)
            body_high = max(data[index].open, data[index].close)
            if body_low < value < body_high:
                violations += 1
        return violations

    @staticmethod
    def _upper_shadow_cross_count(data: Sequence[Bar], points: tuple[Pivot, Pivot, Pivot]) -> int:
        p1, p3 = points[0], points[2]
        count = 0
        for index in range(p1.index, p3.index + 1):
            value = line_value(p1, p3, index)
            if max(data[index].open, data[index].close) <= value <= data[index].high:
                count += 1
        return count

    @staticmethod
    def _open_touch_count(
        data: Sequence[Bar], points: tuple[Pivot, Pivot, Pivot]
    ) -> int:
        p1, p3 = points[0], points[2]
        return sum(
            math.isclose(
                line_value(p1, p3, point.index),
                data[point.index].open,
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
            for point in points
        )

    def _line_contacts(
        self,
        data: Sequence[Bar],
        highs: Sequence[Pivot],
        points: tuple[Pivot, Pivot, Pivot],
        tolerance: float,
    ) -> list[Pivot]:
        p1, p3 = points[0], points[2]
        return [
            high
            for high in highs
            if p1.index <= high.index <= p3.index
            and abs(high.price - line_value(p1, p3, high.index)) <= tolerance
            and self._anchor_contact_is_valid(
                data[high.index], line_value(p1, p3, high.index)
            )
        ]

    @staticmethod
    def _rank(points: tuple[Pivot, Pivot, Pivot]) -> tuple[float, float]:
        return (line_span(points).value, -fit_error(points).value)
