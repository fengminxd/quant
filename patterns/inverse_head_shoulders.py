"""Inverse head-and-shoulders price action pattern."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import InverseHeadShouldersScore
from features.basic import line_value
from indicators.atr import average_true_range
from indicators.swing import Pivot, PivotDetector, SwingDetector


@dataclass(frozen=True)
class InverseHeadShouldersCandidate:
    """Three confirmed swing lows and the two highs forming their neckline."""

    lows: tuple[Pivot, Pivot, Pivot]
    neckline: tuple[Pivot, Pivot]
    atr: float
    breakout_index: int | None
    breakout_distance_atr: float
    breakout_volume_ratio: float


class InverseHeadShoulders(Pattern):
    """Detect selling exhaustion followed by a higher right-shoulder low.

    ``min_span`` uses bar intervals identically for 15m, 1h, and 4h data.
    """

    pattern_id = "PATTERN_007"
    name = "Inverse Head and Shoulders"

    def __init__(
        self,
        swing_detector: SwingDetector | PivotDetector | None = None,
        min_span: int = 40,
        min_leg_span: int = 10,
        min_neckline_leg_span: int = 5,
        min_head_depth_atr: float = 0.5,
        max_shoulder_error_atr: float = 1.0,
        max_head_extreme_error_atr: float = 0.0,
        max_breakout_bars: int = 40,
    ) -> None:
        bar_counts = (min_span, min_leg_span, min_neckline_leg_span, max_breakout_bars)
        if any(value <= 0 for value in bar_counts):
            raise ValueError("bar-count parameters must be positive")
        atr_limits = (min_head_depth_atr, max_shoulder_error_atr, max_head_extreme_error_atr)
        if any(value < 0 for value in atr_limits):
            raise ValueError("ATR thresholds must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(
            PivotDetector(left=5, right=5), min_bars=3
        )
        self.min_span = min_span
        self.min_leg_span = min_leg_span
        self.min_neckline_leg_span = min_neckline_leg_span
        self.min_head_depth_atr = min_head_depth_atr
        self.max_shoulder_error_atr = max_shoulder_error_atr
        self.max_head_extreme_error_atr = max_head_extreme_error_atr
        self.max_breakout_bars = max_breakout_bars
        self.factor = InverseHeadShouldersScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Return the highest-quality structure visible in the supplied bars."""

        candidate, candidate_count = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features_for_candidate(data, candidate, candidate_count)
        left, head, right = candidate.lows
        neck_left, neck_right = candidate.neckline
        breakout_confirmed = candidate.breakout_index is not None
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            self.calculate_score(features),
            features,
            geometry={
                "points": [(point.index, point.price) for point in candidate.lows],
                "point_timestamps": [data[point.index].timestamp for point in candidate.lows],
                "neckline_points": [
                    (neck_left.index, neck_left.price),
                    (neck_right.index, neck_right.price),
                ],
                "neckline_timestamps": [
                    data[neck_left.index].timestamp,
                    data[neck_right.index].timestamp,
                ],
                "breakout_index": candidate.breakout_index,
                "breakout_timestamp": (
                    data[candidate.breakout_index].timestamp if breakout_confirmed else None
                ),
            },
            metadata={
                "rule": "confirmed_three_swing_low_inverse_head_shoulders",
                "state": "breakout_confirmed" if breakout_confirmed else "structure_confirmed",
                "detected_at_index": right.confirmed_at,
                "head_confirmed_at_index": head.confirmed_at,
                "breakout_confirmed_at_index": candidate.breakout_index,
                "timestamp_semantics": "bar_open_time",
                "timeframe": data[right.index].timeframe,
                "min_span_bars": self.min_span,
                "left_shoulder_index": left.index,
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the highest-quality valid structure."""
        candidate, candidate_count = self._best_candidate(data)
        if candidate is None:
            return {}
        return self._features_for_candidate(data, candidate, candidate_count)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Map structure and confirmation features to a score only."""
        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable shoulder, head, neckline, and breakout geometry."""
        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(self, data: Sequence[Bar]) -> tuple[InverseHeadShouldersCandidate | None, int]:
        swings = self.swing_detector.detect(data)
        lows = [pivot for pivot in swings if pivot.kind == "low"]
        highs = [pivot for pivot in swings if pivot.kind == "high"]
        atr_values = average_true_range(data)
        candidates: list[InverseHeadShouldersCandidate] = []
        for left, head, right in combinations(lows, 3):
            if not self._valid_spans(left, head, right):
                continue
            prior_left = data[max(0, left.index - self.min_span) : left.index + 1]
            if left.price != min(bar.low for bar in prior_left):
                continue
            atr = max(atr_values[min(right.confirmed_at, len(data) - 1)], 1e-12)
            if head.price > min(left.price, right.price) - self.min_head_depth_atr * atr:
                continue
            if abs(left.price - right.price) > self.max_shoulder_error_atr * atr:
                continue
            extreme = min(bar.low for bar in data[left.index : right.index + 1])
            if head.price - extreme > self.max_head_extreme_error_atr * atr:
                continue
            neckline = self._neckline(highs, left, head, right)
            if neckline is None:
                continue
            right_pullback = data[neckline[1].index + 1 : right.index + 1]
            if not right_pullback or right.price != min(bar.low for bar in right_pullback):
                continue
            breakout_index, distance, volume_ratio = self._breakout(
                data, atr_values, right, neckline
            )
            candidates.append(
                InverseHeadShouldersCandidate(
                    (left, head, right),
                    neckline,
                    atr,
                    breakout_index,
                    distance,
                    volume_ratio,
                )
            )
        if not candidates:
            return None, 0
        return max(candidates, key=self._rank), len(candidates)

    def _valid_spans(self, left: Pivot, head: Pivot, right: Pivot) -> bool:
        return (
            right.index - left.index >= self.min_span
            and head.index - left.index >= self.min_leg_span
            and right.index - head.index >= self.min_leg_span
        )

    def _neckline(
        self,
        highs: Sequence[Pivot], left: Pivot, head: Pivot, right: Pivot
    ) -> tuple[Pivot, Pivot] | None:
        left_highs = [
            point
            for point in highs
            if point.index - left.index >= self.min_neckline_leg_span
            and head.index - point.index >= self.min_neckline_leg_span
        ]
        right_highs = [
            point
            for point in highs
            if point.index - head.index >= self.min_neckline_leg_span
            and right.index - point.index >= self.min_neckline_leg_span
        ]
        if not left_highs or not right_highs:
            return None
        return max(left_highs, key=lambda point: point.price), max(
            right_highs, key=lambda point: point.price
        )

    def _breakout(
        self,
        data: Sequence[Bar],
        atr_values: Sequence[float],
        right: Pivot,
        neckline: tuple[Pivot, Pivot],
    ) -> tuple[int | None, float, float]:
        start = right.confirmed_at
        end = min(len(data), start + self.max_breakout_bars + 1)
        for index in range(start, end):
            level = line_value(neckline[0], neckline[1], index)
            if data[index].close <= level:
                continue
            atr = max(atr_values[index], 1e-12)
            distance = (data[index].close - level) / atr
            volume_window = data[max(0, index - 20) : index]
            average_volume = (
                sum(bar.volume for bar in volume_window) / len(volume_window)
                if volume_window
                else 0.0
            )
            volume_ratio = data[index].volume / average_volume if average_volume > 0 else 0.0
            return index, distance, volume_ratio
        return None, 0.0, 0.0

    def _features_for_candidate(
        self,
        data: Sequence[Bar],
        candidate: InverseHeadShouldersCandidate,
        candidate_count: int,
    ) -> Mapping[str, FeatureResult]:
        left, head, right = candidate.lows
        neck_left, neck_right = candidate.neckline
        left_leg = head.index - left.index
        right_leg = right.index - head.index
        span = right.index - left.index
        prior = data[max(0, left.index - 20) : left.index]
        prior_decline = max((bar.high for bar in prior), default=left.price) - left.price
        return {
            "span": FeatureResult("span", float(span), 1.0),
            "left_leg_span": FeatureResult("left_leg_span", float(left_leg), 1.0),
            "right_leg_span": FeatureResult("right_leg_span", float(right_leg), 1.0),
            "shoulder_price_error_atr": FeatureResult(
                "shoulder_price_error_atr",
                abs(left.price - right.price) / candidate.atr,
                1.0,
            ),
            "head_depth_atr": FeatureResult(
                "head_depth_atr",
                (min(left.price, right.price) - head.price) / candidate.atr,
                1.0,
            ),
            "head_extreme_error_atr": FeatureResult(
                "head_extreme_error_atr",
                (head.price - min(bar.low for bar in data[left.index : right.index + 1]))
                / candidate.atr,
                1.0,
            ),
            "duration_asymmetry": FeatureResult(
                "duration_asymmetry", abs(left_leg - right_leg) / span, 1.0
            ),
            "neckline_slope_atr_per_bar": FeatureResult(
                "neckline_slope_atr_per_bar",
                (neck_right.price - neck_left.price)
                / (neck_right.index - neck_left.index)
                / candidate.atr,
                1.0,
            ),
            "prior_decline_atr": FeatureResult(
                "prior_decline_atr", prior_decline / candidate.atr, 1.0 if prior else 0.0
            ),
            "breakout_confirmed": FeatureResult(
                "breakout_confirmed", 1.0 if candidate.breakout_index is not None else 0.0, 1.0
            ),
            "breakout_distance_atr": FeatureResult(
                "breakout_distance_atr", candidate.breakout_distance_atr, 1.0
            ),
            "breakout_volume_ratio": FeatureResult(
                "breakout_volume_ratio", candidate.breakout_volume_ratio, 1.0
            ),
            "confirmation_lag": FeatureResult(
                "confirmation_lag", float(right.confirmed_at - right.index), 1.0
            ),
            "valid_candidate_count": FeatureResult(
                "valid_candidate_count", float(candidate_count), 1.0
            ),
        }

    @staticmethod
    def _rank(candidate: InverseHeadShouldersCandidate) -> tuple[float, ...]:
        left, head, right = candidate.lows
        span = right.index - left.index
        duration_asymmetry = abs((head.index - left.index) - (right.index - head.index)) / span
        return (
            1.0 if candidate.breakout_index is not None else 0.0,
            -abs(left.price - right.price) / candidate.atr,
            -duration_asymmetry,
            (min(left.price, right.price) - head.price) / candidate.atr,
            float(span),
            float(right.index),
        )
