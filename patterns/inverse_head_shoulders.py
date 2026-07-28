"""Inverse head-and-shoulders price action pattern."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import InverseHeadShouldersScore
from features.basic import line_value
from indicators.atr import average_true_range
from indicators.swing import Pivot, PivotDetector, SwingDetector
from patterns.inverse_head_shoulders_geometry import (
    InverseHeadShouldersCandidate,
    candidate_features,
    candidate_rank,
    select_neckline,
    valid_leg_spans,
)


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
        min_leg_span_ratio: float | None = 2.0 / 3.0,
        max_neckline_error_atr: float | None = 1.0,
    ) -> None:
        bar_counts = (min_span, min_leg_span, min_neckline_leg_span, max_breakout_bars)
        if any(value <= 0 for value in bar_counts):
            raise ValueError("bar-count parameters must be positive")
        if min_leg_span_ratio is not None and not 0 < min_leg_span_ratio <= 1:
            raise ValueError("min_leg_span_ratio must be in (0, 1]")
        atr_limits = (
            min_head_depth_atr,
            max_shoulder_error_atr,
            max_head_extreme_error_atr,
            *(() if max_neckline_error_atr is None else (max_neckline_error_atr,)),
        )
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
        self.min_leg_span_ratio = min_leg_span_ratio
        self.max_neckline_error_atr = max_neckline_error_atr
        self.factor = InverseHeadShouldersScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Return the highest-quality structure visible in the supplied bars."""

        candidate, candidate_count = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = candidate_features(data, candidate, candidate_count)
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
                "min_leg_span_ratio": self.min_leg_span_ratio,
                "max_neckline_error_atr": self.max_neckline_error_atr,
                "left_shoulder_index": left.index,
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the highest-quality valid structure."""
        candidate, candidate_count = self._best_candidate(data)
        if candidate is None:
            return {}
        return candidate_features(data, candidate, candidate_count)

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
            if not valid_leg_spans(
                left,
                head,
                right,
                min_span=self.min_span,
                min_leg_span=self.min_leg_span,
                min_leg_span_ratio=self.min_leg_span_ratio,
            ):
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
            neckline = select_neckline(
                highs,
                left,
                head,
                right,
                min_leg_span=self.min_neckline_leg_span,
                atr=atr,
                max_price_error_atr=self.max_neckline_error_atr,
            )
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
        return max(candidates, key=candidate_rank), len(candidates)

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
