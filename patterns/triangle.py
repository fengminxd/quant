"""Converging triangle with horizontal or inward-sloping boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import TriangleScore
from features.basic import (
    RegressionLine,
    atr_compression,
    breakout_volume,
    clamp,
    volume_contraction,
)
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector
from patterns.triangle_contacts import cluster_boundary_pivots, include_closed_shadow_contacts
from patterns.triangle_geometry import (
    TriangleCandidate,
    apex_index,
    boundary_candidates,
    candidate_rank,
    combine_boundaries,
    line_geometry,
)


class Triangle(Pattern):
    """Detect converging two-or-three-confirmation price boundaries."""

    pattern_id = "PATTERN_002"
    name = "Triangle"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_boundary_span: int = 5,
        min_overlap_span: int = 5,
        min_adjacent_anchor_span: int = 10,
        max_fit_error_atr: float = 0.5,
        max_anchor_deviation_atr: float = 0.5,
        horizontal_slope_atr_per_bar: float = 0.02,
        min_compression_ratio: float = 0.05,
        max_swings_per_side: int = 16,
        confirmation_cluster_bars: int = 5,
        min_cluster_shadow_ratio: float = 0.25,
        cluster_price_tolerance_atr: float = 0.20,
        max_boundary_breach_atr: float = 0.25,
    ) -> None:
        if min(min_boundary_span, min_overlap_span, min_adjacent_anchor_span) <= 0:
            raise ValueError("span constraints must be positive")
        if min(max_fit_error_atr, max_anchor_deviation_atr, horizontal_slope_atr_per_bar) < 0.0:
            raise ValueError("ATR constraints must be non-negative")
        if not 0.0 < min_compression_ratio < 1.0:
            raise ValueError("min_compression_ratio must be between 0 and 1")
        if max_swings_per_side < 3:
            raise ValueError("max_swings_per_side must be at least 3")
        if confirmation_cluster_bars <= 0:
            raise ValueError("confirmation_cluster_bars must be positive")
        if min(min_cluster_shadow_ratio, cluster_price_tolerance_atr, max_boundary_breach_atr) < 0:
            raise ValueError("cluster thresholds must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.min_boundary_span = min_boundary_span
        self.min_overlap_span = min_overlap_span
        self.min_adjacent_anchor_span = min_adjacent_anchor_span
        self.max_fit_error_atr = max_fit_error_atr
        self.max_anchor_deviation_atr = max_anchor_deviation_atr
        self.horizontal_slope_atr_per_bar = horizontal_slope_atr_per_bar
        self.min_compression_ratio = min_compression_ratio
        self.max_swings_per_side = max_swings_per_side
        self.confirmation_cluster_bars = confirmation_cluster_bars
        self.min_cluster_shadow_ratio = min_cluster_shadow_ratio
        self.cluster_price_tolerance_atr = cluster_price_tolerance_atr
        self.max_boundary_breach_atr = max_boundary_breach_atr
        self.factor = TriangleScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Return the highest-ranked confirmed converging triangle."""

        candidate = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features(data, candidate)
        score = self.calculate_score(features)
        detected_at = max(candidate.highs[-1].confirmed_at, candidate.lows[-1].confirmed_at)
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            score,
            features,
            geometry={
                "upper_points": [(point.index, point.price) for point in candidate.highs],
                "lower_points": [(point.index, point.price) for point in candidate.lows],
                "upper_timestamps": [data[p.index].timestamp for p in candidate.highs],
                "lower_timestamps": [data[point.index].timestamp for point in candidate.lows],
                "upper_line": line_geometry(candidate.upper, candidate.highs),
                "lower_line": line_geometry(candidate.lower, candidate.lows),
                "apex_index": apex_index(candidate),
            },
            metadata={
                "rule": "converging_swing_triangle",
                "triangle_type": self._triangle_type(candidate),
                "state": self._state(features),
                "breakout_direction": self._breakout_direction(features),
                "detected_at_index": detected_at,
                "upper_confirmation_count": len(candidate.highs),
                "lower_confirmation_count": len(candidate.lows),
                "confirmation_cluster_bars": self.confirmation_cluster_bars,
                "confirmation_grouping": "market_leg_with_5_bar_noise_dedup",
                "alternating_boundary_confirmations": True,
                "max_boundary_breach_atr": self.max_boundary_breach_atr,
                "max_anchor_deviation_atr": self.max_anchor_deviation_atr,
                "anchor_alignment_rule": "each_anchor_near_regression_and_endpoint_line",
                "body_breach_rule": "bodies_inside_same_and_opposite_boundaries",
                "confirmation_semantics": "confirmed_swing_or_closed_shadow_contact",
                "quality_threshold_passed": score >= 50.0,
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
        raw_highs = [point for point in swings if point.kind == "high"]
        raw_lows = [point for point in swings if point.kind == "low"]
        if len(raw_highs) < 2 or len(raw_lows) < 2:
            return None
        if len(data) >= 99:
            raw_highs = include_closed_shadow_contacts(
                data,
                raw_highs,
                upper=True,
                lookback_bars=2,
                shadow_ratio=self.min_cluster_shadow_ratio,
            )
            raw_lows = include_closed_shadow_contacts(
                data,
                raw_lows,
                upper=False,
                lookback_bars=2,
                shadow_ratio=self.min_cluster_shadow_ratio,
            )
        atr = max(average_true_range(data)[-1], 1e-12)
        highs = self._cluster(data, raw_highs, atr, upper=True, opposite=raw_lows)[-self.max_swings_per_side :]
        lows = self._cluster(data, raw_lows, atr, upper=False, opposite=raw_highs)[-self.max_swings_per_side :]
        upper_candidates = self._boundary_candidates(highs, atr, upper=True)
        lower_candidates = self._boundary_candidates(lows, atr, upper=False)
        candidates: list[TriangleCandidate] = []
        for high_points, upper in upper_candidates:
            for low_points, lower in lower_candidates:
                candidate = combine_boundaries(
                    data,
                    highs,
                    lows,
                    high_points,
                    low_points,
                    upper,
                    lower,
                    atr,
                    min_overlap_span=self.min_overlap_span,
                    min_adjacent_anchor_span=self.min_adjacent_anchor_span,
                    min_compression_ratio=self.min_compression_ratio,
                    max_boundary_breach_atr=self.max_boundary_breach_atr,
                )
                if candidate is not None:
                    candidates.append(candidate)
        return max(candidates, key=candidate_rank) if candidates else None

    def _cluster(
        self, data: Sequence[Bar], points: Sequence[Pivot], atr: float, *, upper: bool,
        opposite: Sequence[Pivot] = (),
    ) -> list[Pivot]:
        return cluster_boundary_pivots(
            data,
            points,
            atr,
            upper=upper,
            cluster_bars=self.confirmation_cluster_bars,
            shadow_ratio=self.min_cluster_shadow_ratio,
            price_tolerance_atr=self.cluster_price_tolerance_atr,
            opposite_points=opposite,
        )

    def _boundary_candidates(
        self, points: Sequence[Pivot], atr: float, *, upper: bool
    ) -> list[tuple[tuple[Pivot, ...], RegressionLine]]:
        return boundary_candidates(
            points,
            atr,
            upper=upper,
            min_span=self.min_boundary_span,
            max_fit_error_atr=self.max_fit_error_atr,
            max_anchor_deviation_atr=self.max_anchor_deviation_atr,
            horizontal_slope_atr_per_bar=self.horizontal_slope_atr_per_bar,
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
            "upper_confirmation_count": FeatureResult(
                "upper_confirmation_count", float(len(candidate.highs)), 1.0
            ),
            "lower_confirmation_count": FeatureResult(
                "lower_confirmation_count", float(len(candidate.lows)), 1.0
            ),
            "boundary_confirmation_score": FeatureResult(
                "boundary_confirmation_score",
                100.0 if len(candidate.highs) + len(candidate.lows) == 6 else 80.0,
                1.0,
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
