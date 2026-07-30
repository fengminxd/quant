"""Strict three-point trendline support pattern."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import ThreePointTrendlineSupportScore
from features.basic import line_span, line_value, normalized_log_trend_features, trend_angle
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector
from patterns.lower_shadow_trendline import (
    ThreePointSupportCandidate,
    fit_lower_shadow_line,
    lower_shadow_contact_is_valid,
    support_body_violation_count,
)


class ThreePointTrendlineSupport(Pattern):
    """Support established by P1-P2 and confirmed by a P3 lower-shadow retest."""
    pattern_id = "PATTERN_003"
    name = "Three Point Trendline Support"
    max_normalized_trend_strength = 0.16

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_total_span: int = 50,
        min_leg_span: int = 15,
        atr_tolerance_ratio: float = 0.65,
    ) -> None:
        if min_total_span <= 0 or min_leg_span <= 0:
            raise ValueError("span constraints must be positive")
        if atr_tolerance_ratio < 0:
            raise ValueError("atr_tolerance_ratio must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.min_total_span = min_total_span
        self.min_leg_span = min_leg_span
        self.atr_tolerance_ratio = atr_tolerance_ratio
        self.factor = ThreePointTrendlineSupportScore(min_total_span)

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the highest-quality strict three-point support."""
        candidate = self._best_candidate(data)
        return self._result(data, candidate)

    def detect_at(self, data: Sequence[Bar], anchor_index: int) -> PatternResult:
        """Detect support whose third confirmed swing is ``anchor_index``."""
        if anchor_index < 0 or anchor_index >= len(data):
            raise ValueError("anchor_index is outside supplied data")
        candidate = self._best_candidate(data, anchor_index)
        return self._result(data, candidate, anchor_index)

    def detect_anchors(
        self,
        data: Sequence[Bar],
        anchor_indexes: tuple[int, int, int],
        max_confirmation_offset: int = 1,
    ) -> PatternResult:
        """Validate supplied contacts against exact or adjacent confirmed lows."""
        if len(anchor_indexes) != 3:
            raise ValueError("exactly three anchor_indexes are required")
        if max_confirmation_offset < 0:
            raise ValueError("max_confirmation_offset must be non-negative")
        if not (anchor_indexes[0] < anchor_indexes[1] < anchor_indexes[2]):
            raise ValueError("anchor_indexes must be strictly increasing")
        if anchor_indexes[0] < 0 or anchor_indexes[-1] >= len(data):
            raise ValueError("anchor_indexes are outside supplied data")
        event_index = anchor_indexes[-1]
        atr = average_true_range(data[: event_index + 1])[-1]
        tolerance = max(1e-9, atr * self.atr_tolerance_ratio)
        confirmed_lows = self.swing_detector.lows(data)
        resolved: list[Pivot] = []
        source_indexes: list[int] = []
        for index in anchor_indexes:
            matches = [
                pivot
                for pivot in confirmed_lows
                if 0 <= pivot.index - index <= max_confirmation_offset
                and abs(pivot.price - data[index].low) <= tolerance
            ]
            if not matches:
                return PatternResult(
                    self.pattern_id,
                    self.name,
                    False,
                    0.0,
                    metadata={"event_index": event_index, "anchor_indexes": anchor_indexes},
                )
            source = min(
                matches,
                key=lambda pivot: (pivot.index - index, abs(pivot.price - data[index].low)),
            )
            resolved.append(Pivot(index, source.confirmed_at, data[index].low, "low"))
            source_indexes.append(source.index)
        points = (resolved[0], resolved[1], resolved[2])
        candidate = self._candidate_for_points(data, points, tolerance)
        if candidate is None:
            return PatternResult(
                self.pattern_id,
                self.name,
                False,
                0.0,
                metadata={"event_index": event_index, "anchor_indexes": anchor_indexes},
            )
        result = self._result(data, candidate, event_index)
        metadata = dict(result.metadata)
        metadata.update(
            {
                "anchor_mode": "supplied_confirmed_swing_zone",
                "resolved_swing_indexes": tuple(source_indexes),
                "anchor_confirmation_offsets": tuple(
                    source - anchor
                    for source, anchor in zip(source_indexes, anchor_indexes)
                ),
            }
        )
        return PatternResult(
            result.pattern_id,
            result.name,
            result.detected,
            result.score,
            result.features,
            result.geometry,
            metadata,
        )

    def _result(
        self,
        data: Sequence[Bar],
        candidate: ThreePointSupportCandidate | None,
        anchor_index: int | None = None,
    ) -> PatternResult:
        if candidate is None:
            metadata = {"event_index": anchor_index} if anchor_index is not None else {}
            return PatternResult(self.pattern_id, self.name, False, 0.0, metadata=metadata)
        features = self._features_for_candidate(data, candidate)
        score = self.calculate_score(features)
        points = candidate.points
        line_points = candidate.line_points
        projected_p3 = line_points[2].price
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            score,
            features,
            geometry={
                "points": [(point.index, point.price) for point in points],
                "line_contacts": [(point.index, point.price) for point in line_points],
                "point_timestamps": [data[point.index].timestamp for point in points],
                "line": {
                    "start": (line_points[0].index, line_points[0].price),
                    "end": (points[2].index, projected_p3),
                },
            },
            metadata={
                "rule": "strict_three_point_slope_support",
                "timestamp_semantics": "bar_open_time",
                "event_index": points[2].index,
                "detected_at_index": points[2].confirmed_at,
                "line_definition": "p1_p2_lower_shadow_contacts_projected_to_p3",
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

    def _best_candidate(
        self, data: Sequence[Bar], anchor_index: int | None = None
    ) -> ThreePointSupportCandidate | None:
        # Only confirmed swing lows are eligible; never synthesize the last bar.
        lows = self.swing_detector.lows(data)
        if len(lows) < 3:
            return None
        atr_values = average_true_range(data)
        candidates: list[ThreePointSupportCandidate] = []
        for combo in combinations(lows, 3):
            points = (combo[0], combo[1], combo[2])
            if anchor_index is not None and points[2].index != anchor_index:
                continue
            tolerance = max(1e-9, atr_values[points[2].index] * self.atr_tolerance_ratio)
            candidate = self._candidate_for_points(data, points, tolerance)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: self._rank(candidate))

    def _candidate_for_points(
        self,
        data: Sequence[Bar],
        points: tuple[Pivot, Pivot, Pivot],
        tolerance: float,
    ) -> ThreePointSupportCandidate | None:
        if not self._passes_geometry(points):
            return None
        if normalized_log_trend_features(data, points)[
            "normalized_trend_strength"
        ].value > self.max_normalized_trend_strength + 1e-12:
            return None
        fitted = fit_lower_shadow_line(data, points, tolerance)
        if fitted is None:
            return None
        candidate = ThreePointSupportCandidate(points, fitted.contacts, tolerance)
        if self._body_violation_count(data, candidate) > 0:
            return None
        return candidate

    def _features_for_candidate(
        self,
        data: Sequence[Bar],
        candidate: ThreePointSupportCandidate,
    ) -> Mapping[str, FeatureResult]:
        points = candidate.points
        line_points = candidate.line_points
        p1, p2, p3 = line_points
        atr = average_true_range(data[: points[2].index + 1])[-1]
        slope = (p2.price - p1.price) / (p2.index - p1.index)
        projected_p3 = p3.price
        adjustments = [
            abs(contact.price - swing.price)
            for contact, swing in zip(line_points, points)
        ]
        projection_error = adjustments[2]
        mean_error = sum(adjustments) / len(points)
        return {
            **normalized_log_trend_features(data, points),
            "touch_count": FeatureResult("touch_count", 3.0, 1.0),
            "line_span": line_span(points),
            "leg_1_span": FeatureResult(
                "leg_1_span", float(points[1].index - points[0].index), 1.0
            ),
            "leg_2_span": FeatureResult(
                "leg_2_span", float(points[2].index - points[1].index), 1.0
            ),
            "line_slope": FeatureResult("line_slope", slope, 1.0),
            "line_angle": trend_angle((p1, p2)),
            "p3_projection_price": FeatureResult("p3_projection_price", projected_p3, 1.0),
            "p3_projection_error": FeatureResult("p3_projection_error", projection_error, 1.0),
            "p1_anchor_adjustment": FeatureResult(
                "p1_anchor_adjustment", adjustments[0], 1.0
            ),
            "p2_anchor_adjustment": FeatureResult(
                "p2_anchor_adjustment", adjustments[1], 1.0
            ),
            "fit_error": FeatureResult("fit_error", mean_error, 1.0),
            "fit_error_atr": FeatureResult(
                "fit_error_atr", mean_error / atr if atr > 0 else 0.0, 1.0
            ),
            "body_violation_count": FeatureResult("body_violation_count",
                float(self._body_violation_count(data, candidate)), 1.0),
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
    def _anchor_contact_is_valid(bar: Bar, value: float) -> bool:
        return lower_shadow_contact_is_valid(bar, value)

    @staticmethod
    def _body_violation_count(
        data: Sequence[Bar], candidate: ThreePointSupportCandidate
    ) -> int:
        return support_body_violation_count(data, candidate.points, candidate.line_points)

    @staticmethod
    def _rank(candidate: ThreePointSupportCandidate) -> tuple[float, float]:
        adjustment = sum(
            abs(contact.price - swing.price)
            for contact, swing in zip(candidate.line_points, candidate.points)
        )
        return line_span(candidate.points).value, -adjustment
