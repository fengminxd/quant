"""Horizontal support pattern definitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from features.basic import clamp
from indicators.atr import average_true_range
from indicators.swing import PivotDetector, SwingDetector
from patterns.horizontal_support_candidates import (
    HorizontalSupportCandidate,
    HorizontalSupportCandidateFinder,
)


class HorizontalSupport(Pattern):
    """Detect horizontal support and breakout-retest support."""

    pattern_id = "PATTERN_004"
    name = "Horizontal Support"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_span: int = 40,
        breakout_hold_atr_tolerance_ratio: float = 0.1,
        price_epsilon: float = 1e-9,
    ) -> None:
        if min_span <= 0:
            raise ValueError("min_span must be positive")
        if min(
            breakout_hold_atr_tolerance_ratio,
            price_epsilon,
        ) < 0:
            raise ValueError("price tolerances must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(
            PivotDetector(left=5, right=5), min_bars=3
        )
        self.min_span = min_span
        self.breakout_hold_atr_tolerance_ratio = (
            breakout_hold_atr_tolerance_ratio
        )
        self.price_epsilon = price_epsilon
        self.candidate_finder = HorizontalSupportCandidateFinder(
            self.swing_detector,
            min_span,
            breakout_hold_atr_tolerance_ratio,
            price_epsilon,
        )

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the highest-quality horizontal support candidate."""

        candidate = self._best_candidate(data)
        return self._result(data, candidate)

    def detect_at(self, data: Sequence[Bar], anchor_index: int) -> PatternResult:
        """Detect horizontal support whose right anchor is ``anchor_index``."""

        if anchor_index < 0 or anchor_index >= len(data):
            raise ValueError("anchor_index is outside supplied data")
        candidate = self._best_candidate(data, anchor_index)
        return self._result(data, candidate, anchor_index)

    def _result(
        self,
        data: Sequence[Bar],
        candidate: HorizontalSupportCandidate | None,
        anchor_index: int | None = None,
    ) -> PatternResult:
        if candidate is None:
            metadata = {"event_index": anchor_index} if anchor_index is not None else {}
            return PatternResult(self.pattern_id, self.name, False, 0.0, metadata=metadata)
        features = self._features_for_candidate(data, candidate)
        right = candidate.points[1]
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            self.calculate_score(features),
            features,
            geometry={
                "level": candidate.level,
                "points": [(point.index, point.price) for point in candidate.points],
                "contact_points": [
                    (point.index, candidate.level) for point in candidate.points
                ],
                "point_timestamps": [data[point.index].timestamp for point in candidate.points],
                "breakout_index": candidate.breakout_index,
                "breakout_timestamp": (
                    data[candidate.breakout_index].timestamp
                    if candidate.breakout_index is not None else None
                ),
            },
            metadata={
                "rule_type": candidate.rule_type,
                "contact_rule": "traded_zone_overlap",
                "event_index": right.index,
                "detected_at_index": right.confirmed_at,
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features from the best candidate."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features_for_candidate(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Calculate a 0-100 structural score."""

        span_score = clamp(features["span"].value / self.min_span * 100.0)
        pierce_penalty = clamp(features["pierce_count"].value * 50.0)
        level_error_score = max(0.0, 100.0 - features["level_error_atr"].value * 100.0)
        return round(
            0.45 * span_score
            + 0.35 * level_error_score
            + 0.20 * (100.0 - pierce_penalty),
            4,
        )

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable support geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(
        self, data: Sequence[Bar], anchor_index: int | None = None
    ) -> HorizontalSupportCandidate | None:
        return self.candidate_finder.best(data, anchor_index)

    def _features_for_candidate(
        self, data: Sequence[Bar], candidate: HorizontalSupportCandidate
    ) -> Mapping[str, FeatureResult]:
        left, right = candidate.points
        atr = max(average_true_range(data[: right.index + 1])[-1], 1e-12)
        return {
            "rule_type": FeatureResult(
                "rule_type",
                1.0 if candidate.rule_type == "breakout_retest" else 0.0,
                1.0,
            ),
            "span": FeatureResult("span", float(right.index - left.index), 1.0),
            "level": FeatureResult("level", candidate.level, 1.0),
            "pierce_count": FeatureResult("pierce_count", float(candidate.pierce_count), 1.0),
            "level_error": FeatureResult("level_error", candidate.level_error, 1.0),
            "level_error_atr": FeatureResult(
                "level_error_atr",
                candidate.level_error / atr,
                1.0,
            ),
            "contact_overlap_atr": FeatureResult(
                "contact_overlap_atr",
                candidate.contact_overlap / atr,
                1.0,
            ),
            "contact_tolerance_atr": FeatureResult(
                "contact_tolerance_atr",
                candidate.contact_tolerance / atr,
                1.0,
            ),
            "hold_tolerance_atr": FeatureResult(
                "hold_tolerance_atr",
                candidate.hold_tolerance / atr,
                1.0,
            ),
            "breakout_index": FeatureResult(
                "breakout_index",
                float(candidate.breakout_index if candidate.breakout_index is not None else -1),
                1.0,
            ),
            "retest_close_distance_atr": FeatureResult(
                "retest_close_distance_atr",
                (data[right.index].close - candidate.level) / atr,
                1.0,
            ),
        }
