"""Converging triangle with horizontal or inward-sloping boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import TriangleScore
from features.basic import (
    RegressionLine,
    atr_compression,
    breakout_volume,
    clamp,
    fit_regression_line,
    volume_contraction,
)
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector


@dataclass(frozen=True)
class TriangleCandidate:
    """Two fitted and converging three-pivot triangle boundaries."""

    highs: tuple[Pivot, Pivot, Pivot]
    lows: tuple[Pivot, Pivot, Pivot]
    upper: RegressionLine
    lower: RegressionLine
    overlap_start: int
    overlap_end: int
    compression_ratio: float
    atr: float


class Triangle(Pattern):
    """Detect horizontal/descending highs against horizontal/rising lows."""

    pattern_id = "PATTERN_002"
    name = "Triangle"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_boundary_span: int = 5,
        min_overlap_span: int = 5,
        max_fit_error_atr: float = 0.5,
        horizontal_slope_atr_per_bar: float = 0.02,
        min_compression_ratio: float = 0.05,
        max_swings_per_side: int = 8,
    ) -> None:
        if min_boundary_span <= 0 or min_overlap_span <= 0:
            raise ValueError("span constraints must be positive")
        if max_fit_error_atr < 0.0 or horizontal_slope_atr_per_bar < 0.0:
            raise ValueError("ATR constraints must be non-negative")
        if not 0.0 < min_compression_ratio < 1.0:
            raise ValueError("min_compression_ratio must be between 0 and 1")
        if max_swings_per_side < 3:
            raise ValueError("max_swings_per_side must be at least 3")
        self.swing_detector = swing_detector or SwingDetector(min_bars=3)
        self.min_boundary_span = min_boundary_span
        self.min_overlap_span = min_overlap_span
        self.max_fit_error_atr = max_fit_error_atr
        self.horizontal_slope_atr_per_bar = horizontal_slope_atr_per_bar
        self.min_compression_ratio = min_compression_ratio
        self.max_swings_per_side = max_swings_per_side
        self.factor = TriangleScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Return the highest-ranked confirmed converging triangle."""

        candidate = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features(data, candidate)
        score = self.calculate_score(features)
        detected_at = max(
            candidate.highs[-1].confirmed_at,
            candidate.lows[-1].confirmed_at,
        )
        return PatternResult(
            self.pattern_id,
            self.name,
            score >= 50.0,
            score,
            features,
            geometry={
                "upper_points": [(point.index, point.price) for point in candidate.highs],
                "lower_points": [(point.index, point.price) for point in candidate.lows],
                "upper_timestamps": [data[point.index].timestamp for point in candidate.highs],
                "lower_timestamps": [data[point.index].timestamp for point in candidate.lows],
                "upper_line": self._line_geometry(candidate.upper, candidate.highs),
                "lower_line": self._line_geometry(candidate.lower, candidate.lows),
                "apex_index": self._apex_index(candidate),
            },
            metadata={
                "rule": "converging_swing_triangle",
                "triangle_type": self._triangle_type(candidate),
                "state": self._state(features),
                "breakout_direction": self._breakout_direction(features),
                "detected_at_index": detected_at,
                "timestamp_semantics": "bar_open_time",
                "timeframe": data[-1].timeframe,
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the highest-ranked valid triangle."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Map triangle geometry and market behavior to a 0-100 score."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable triangle lines and score."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(self, data: Sequence[Bar]) -> TriangleCandidate | None:
        swings = self.swing_detector.detect(data)
        highs = [point for point in swings if point.kind == "high"][-self.max_swings_per_side :]
        lows = [point for point in swings if point.kind == "low"][-self.max_swings_per_side :]
        if len(highs) < 3 or len(lows) < 3:
            return None
        atr = max(average_true_range(data)[-1], 1e-12)
        upper_candidates = self._boundary_candidates(highs, atr, upper=True)
        lower_candidates = self._boundary_candidates(lows, atr, upper=False)
        candidates: list[TriangleCandidate] = []
        for high_points, upper in upper_candidates:
            for low_points, lower in lower_candidates:
                candidate = self._combine(
                    highs, lows, high_points, low_points, upper, lower, atr
                )
                if candidate is not None:
                    candidates.append(candidate)
        return max(candidates, key=self._rank) if candidates else None

    def _boundary_candidates(
        self, points: Sequence[Pivot], atr: float, *, upper: bool
    ) -> list[tuple[tuple[Pivot, Pivot, Pivot], RegressionLine]]:
        candidates: list[tuple[tuple[Pivot, Pivot, Pivot], RegressionLine]] = []
        for combo in combinations(points, 3):
            if combo[-1].index - combo[0].index < self.min_boundary_span:
                continue
            line = fit_regression_line(combo)
            normalized_slope = line.slope / atr
            slope_valid = (
                normalized_slope <= self.horizontal_slope_atr_per_bar
                if upper
                else normalized_slope >= -self.horizontal_slope_atr_per_bar
            )
            if slope_valid and line.rmse / atr <= self.max_fit_error_atr:
                candidates.append((combo, line))
        return candidates

    def _combine(
        self,
        all_highs: Sequence[Pivot],
        all_lows: Sequence[Pivot],
        highs: tuple[Pivot, Pivot, Pivot],
        lows: tuple[Pivot, Pivot, Pivot],
        upper: RegressionLine,
        lower: RegressionLine,
        atr: float,
    ) -> TriangleCandidate | None:
        overlap_start = max(highs[0].index, lows[0].index)
        overlap_end = min(highs[-1].index, lows[-1].index)
        if overlap_end - overlap_start < self.min_overlap_span:
            return None
        gap_start = upper.value_at(overlap_start) - lower.value_at(overlap_start)
        gap_end = upper.value_at(overlap_end) - lower.value_at(overlap_end)
        if gap_start <= 0.0 or gap_end <= 0.0:
            return None
        compression = (gap_start - gap_end) / gap_start
        if compression < self.min_compression_ratio:
            return None
        tolerance = self.max_fit_error_atr * atr
        if any(
            point.price > upper.value_at(point.index) + tolerance
            for point in all_highs
            if overlap_start <= point.index <= overlap_end
        ):
            return None
        if any(
            point.price < lower.value_at(point.index) - tolerance
            for point in all_lows
            if overlap_start <= point.index <= overlap_end
        ):
            return None
        return TriangleCandidate(
            highs, lows, upper, lower, overlap_start, overlap_end, compression, atr
        )

    def _features(
        self, data: Sequence[Bar], candidate: TriangleCandidate
    ) -> Mapping[str, FeatureResult]:
        upper_slope = candidate.upper.slope / candidate.atr
        lower_slope = candidate.lower.slope / candidate.atr
        fit_error = (candidate.upper.rmse + candidate.lower.rmse) / 2.0 / candidate.atr
        latest_upper = candidate.upper.value_at(len(data) - 1)
        latest_lower = candidate.lower.value_at(len(data) - 1)
        upside = max(0.0, data[-1].close - latest_upper) / candidate.atr
        downside = max(0.0, latest_lower - data[-1].close) / candidate.atr
        return {
            "upper_slope_atr_per_bar": FeatureResult(
                "upper_slope_atr_per_bar", upper_slope, 1.0
            ),
            "lower_slope_atr_per_bar": FeatureResult(
                "lower_slope_atr_per_bar", lower_slope, 1.0
            ),
            "upper_fit_error_atr": FeatureResult(
                "upper_fit_error_atr", candidate.upper.rmse / candidate.atr, 1.0
            ),
            "lower_fit_error_atr": FeatureResult(
                "lower_fit_error_atr", candidate.lower.rmse / candidate.atr, 1.0
            ),
            "boundary_direction_score": FeatureResult(
                "boundary_direction_score", 100.0, 1.0
            ),
            "boundary_fit_score": FeatureResult(
                "boundary_fit_score", clamp(100.0 - fit_error * 100.0), 1.0
            ),
            "convergence_ratio": FeatureResult(
                "convergence_ratio", candidate.compression_ratio, 1.0
            ),
            "convergence_score": FeatureResult(
                "convergence_score", clamp(candidate.compression_ratio * 200.0), 1.0
            ),
            "overlap_span": FeatureResult(
                "overlap_span", float(candidate.overlap_end - candidate.overlap_start), 1.0
            ),
            "atr_compression": atr_compression(data),
            "volume_contraction": volume_contraction(data),
            "breakout_strength": FeatureResult(
                "breakout_strength", clamp(max(upside, downside) * 100.0), 1.0
            ),
            "upside_breakout_strength": FeatureResult(
                "upside_breakout_strength", clamp(upside * 100.0), 1.0
            ),
            "downside_breakdown_strength": FeatureResult(
                "downside_breakdown_strength", clamp(downside * 100.0), 1.0
            ),
            "breakout_volume": breakout_volume(data),
        }

    def _triangle_type(self, candidate: TriangleCandidate) -> str:
        tolerance = self.horizontal_slope_atr_per_bar
        upper_horizontal = abs(candidate.upper.slope / candidate.atr) <= tolerance
        lower_horizontal = abs(candidate.lower.slope / candidate.atr) <= tolerance
        if upper_horizontal and not lower_horizontal:
            return "ascending_triangle"
        if lower_horizontal and not upper_horizontal:
            return "descending_triangle"
        return "symmetrical_triangle"

    @staticmethod
    def _state(features: Mapping[str, FeatureResult]) -> str:
        direction = Triangle._breakout_direction(features)
        return f"{direction}_breakout_confirmed" if direction else "structure_confirmed"

    @staticmethod
    def _breakout_direction(features: Mapping[str, FeatureResult]) -> str | None:
        if features["upside_breakout_strength"].value > 0.0:
            return "upside"
        if features["downside_breakdown_strength"].value > 0.0:
            return "downside"
        return None

    @staticmethod
    def _line_geometry(
        line: RegressionLine, points: Sequence[Pivot]
    ) -> Mapping[str, tuple[int, float]]:
        return {
            "start": (points[0].index, line.value_at(points[0].index)),
            "end": (points[-1].index, line.value_at(points[-1].index)),
        }

    @staticmethod
    def _apex_index(candidate: TriangleCandidate) -> float | None:
        slope_difference = candidate.upper.slope - candidate.lower.slope
        if abs(slope_difference) <= 1e-12:
            return None
        return (candidate.lower.intercept - candidate.upper.intercept) / slope_difference

    @staticmethod
    def _rank(candidate: TriangleCandidate) -> tuple[float, float, float, float]:
        overlap = candidate.overlap_end - candidate.overlap_start
        fit_error = candidate.upper.rmse + candidate.lower.rmse
        total_span = max(candidate.highs[-1].index, candidate.lows[-1].index) - min(
            candidate.highs[0].index, candidate.lows[0].index
        )
        return (float(overlap), candidate.compression_ratio, -fit_error, float(total_span))
