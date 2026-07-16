"""Horizontal support pattern definitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from features.basic import clamp
from indicators.atr import average_true_range
from indicators.swing import Pivot, PivotDetector, SwingDetector
from patterns.support_levels import (
    all_closes_above_level,
    body_pierce_count,
    first_accepted_breakout,
    lower_support_levels,
    matching_level,
    post_breakout_closes_hold,
    upper_resistance_levels,
)


@dataclass(frozen=True)
class HorizontalSupportCandidate:
    """Horizontal support candidate from two swing anchors."""

    rule_type: str
    points: tuple[Pivot, Pivot]
    level: float
    tolerance: float
    pierce_count: int
    level_error: float
    breakout_index: int | None = None


class HorizontalSupport(Pattern):
    """Detect horizontal support and breakout-retest support."""

    pattern_id = "PATTERN_004"
    name = "Horizontal Support"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_span: int = 40,
        atr_tolerance_ratio: float = 0.6,
    ) -> None:
        if min_span <= 0:
            raise ValueError("min_span must be positive")
        if atr_tolerance_ratio < 0:
            raise ValueError("atr_tolerance_ratio must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(
            PivotDetector(left=5, right=5), min_bars=3
        )
        self.min_span = min_span
        self.atr_tolerance_ratio = atr_tolerance_ratio

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
                "point_timestamps": [data[point.index].timestamp for point in candidate.points],
                "breakout_index": candidate.breakout_index,
                "breakout_timestamp": (
                    data[candidate.breakout_index].timestamp
                    if candidate.breakout_index is not None else None
                ),
            },
            metadata={
                "rule_type": candidate.rule_type,
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
        swings = self.swing_detector.detect(data)
        swings = self._with_boundary_swings(data, swings)
        atr = average_true_range(data)[-1]
        tolerance = max(1e-9, atr * self.atr_tolerance_ratio)
        candidates = self._double_low_candidates(data, swings, tolerance)
        candidates.extend(self._breakout_retest_candidates(data, swings, tolerance))
        if anchor_index is not None:
            candidates = [
                candidate for candidate in candidates
                if candidate.points[1].index == anchor_index
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: self._rank(candidate))

    def _with_boundary_swings(self, data: Sequence[Bar], swings: Sequence[Pivot]) -> list[Pivot]:
        merged = list(swings)
        if not data:
            return merged
        right = getattr(self.swing_detector.pivot_detector, "right", 2)
        left = getattr(self.swing_detector.pivot_detector, "left", 2)
        if len(data) > right:
            first_window = data[: right + 1]
            if data[0].high == max(bar.high for bar in first_window):
                merged.append(Pivot(0, right, data[0].high, "high"))
            if data[0].low == min(bar.low for bar in first_window):
                merged.append(Pivot(0, right, data[0].low, "low"))
        if len(data) > left:
            last_index = len(data) - 1
            last_window = data[last_index - left :]
            if data[last_index].low == min(bar.low for bar in last_window):
                merged.append(Pivot(last_index, last_index, data[last_index].low, "low"))
        return sorted(set(merged), key=lambda pivot: (pivot.index, pivot.kind, pivot.price))

    def _double_low_candidates(
        self,
        data: Sequence[Bar],
        swings: Sequence[Pivot],
        tolerance: float,
    ) -> list[HorizontalSupportCandidate]:
        lows = [pivot for pivot in swings if pivot.kind == "low"]
        candidates: list[HorizontalSupportCandidate] = []
        for left, right in combinations(lows, 2):
            if right.index - left.index < self.min_span:
                continue
            match = matching_level(
                lower_support_levels(data[left.index]),
                lower_support_levels(data[right.index]),
                tolerance,
            )
            if match is None:
                continue
            level, level_error = match
            if body_pierce_count(data, left.index, right.index, level) != 0:
                continue
            if not all_closes_above_level(data, left.index, right.index, level, tolerance):
                continue
            candidates.append(
                HorizontalSupportCandidate(
                    "double_swing_low", (left, right), level, tolerance, 0, level_error
                )
            )
        return candidates

    def _breakout_retest_candidates(
        self,
        data: Sequence[Bar],
        swings: Sequence[Pivot],
        tolerance: float,
    ) -> list[HorizontalSupportCandidate]:
        highs = [pivot for pivot in swings if pivot.kind == "high"]
        lows = [pivot for pivot in swings if pivot.kind == "low"]
        candidates: list[HorizontalSupportCandidate] = []
        for high in highs:
            for low in lows:
                if low.index <= high.index or low.index - high.index < self.min_span:
                    continue
                match = matching_level(
                    upper_resistance_levels(data[high.index]),
                    lower_support_levels(data[low.index]),
                    tolerance,
                )
                if match is None:
                    continue
                level, level_error = match
                breakout_index = first_accepted_breakout(
                    data, high.index + 1, low.index, level
                )
                if breakout_index is None:
                    continue
                if not post_breakout_closes_hold(
                    data, high.index, breakout_index, low.index, level, tolerance
                ):
                    continue
                candidates.append(
                    HorizontalSupportCandidate(
                        "breakout_retest", (high, low), level, tolerance,
                        1, level_error, breakout_index,
                    )
                )
        return candidates

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
                candidate.level_error / candidate.tolerance * 0.1,
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

    @staticmethod
    def _rank(
        candidate: HorizontalSupportCandidate,
    ) -> tuple[float, float, float, float]:
        left, right = candidate.points
        rule_priority = 1.0 if candidate.rule_type == "breakout_retest" else 0.0
        recency_or_span = (
            float(left.index)
            if candidate.breakout_index is not None
            else float(right.index - left.index)
        )
        return (
            rule_priority,
            recency_or_span,
            -candidate.level_error,
            -float(candidate.pierce_count),
        )
