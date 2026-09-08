"""Parallel price channel confirmed by asymmetric swing anchors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import ParallelChannelScore
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector
from patterns.parallel_channel_geometry import (
    ChannelBoundary,
    ParallelChannelCandidate,
    ParallelChannelGeometry,
)


class ParallelChannel(Pattern):
    """Detect two same-slope shadow boundaries with 3+2 swing anchors."""

    pattern_id = "PATTERN_009"
    name = "Parallel Channel"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_channel_span: int = 100,
        min_anchor_spacing: int = 15,
        atr_tolerance_ratio: float = 0.65,
        max_body_violations: int = 0,
    ) -> None:
        if min_channel_span <= 0 or min_anchor_spacing <= 0:
            raise ValueError("span constraints must be positive")
        if atr_tolerance_ratio < 0.0:
            raise ValueError("atr_tolerance_ratio must be non-negative")
        if max_body_violations < 0:
            raise ValueError("max_body_violations must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.geometry_detector = ParallelChannelGeometry(
            min_channel_span,
            min_anchor_spacing,
            atr_tolerance_ratio,
            max_body_violations,
        )
        self.factor = ParallelChannelScore(min_channel_span)

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Return the highest-ranked channel visible in ``data``."""

        candidate = self._best_candidate(data)
        return self._result(data, candidate)

    def detect_at(self, data: Sequence[Bar], anchor_index: int) -> PatternResult:
        """Return the best channel using ``anchor_index`` on either boundary."""

        if anchor_index < 0 or anchor_index >= len(data):
            raise ValueError("anchor_index is outside supplied data")
        candidate = self._best_candidate(data, required_anchor_index=anchor_index)
        return self._result(data, candidate)

    def _result(
        self,
        data: Sequence[Bar],
        candidate: ParallelChannelCandidate | None,
    ) -> PatternResult:
        """Build the public result contract for one channel candidate."""

        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features(data, candidate)
        lower, upper = candidate.lower, candidate.upper
        start, end = candidate.start_index, candidate.end_index
        anchors = lower.anchors + upper.anchors
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            self.calculate_score(features),
            features,
            geometry={
                "lower_points": self._raw_points(lower.anchors),
                "upper_points": self._raw_points(upper.anchors),
                "lower_contacts": self._line_points(lower),
                "upper_contacts": self._line_points(upper),
                "lower_line": self._line_geometry(lower, start, end),
                "upper_line": self._line_geometry(upper, start, end),
            },
            metadata={
                "rule": "parallel_channel_3_plus_2_confirmed_swings",
                "timestamp_semantics": "bar_open_time",
                "event_index": max(point.index for point in anchors),
                "detected_at_index": max(point.confirmed_at for point in anchors),
                "structure_span_bars": end - start,
                "anchor_definition": "confirmed_swing_shadow_contact",
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract features for the highest-ranked valid channel."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Return a direction-neutral structural score in the 0-100 range."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable two-boundary geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(
        self,
        data: Sequence[Bar],
        required_anchor_index: int | None = None,
    ) -> ParallelChannelCandidate | None:
        if len(data) < 5:
            return None
        return self.geometry_detector.best(
            data,
            self.swing_detector.lows(data),
            self.swing_detector.highs(data),
            average_true_range(data),
            required_anchor_index=required_anchor_index,
        )

    @staticmethod
    def _features(
        data: Sequence[Bar], candidate: ParallelChannelCandidate
    ) -> Mapping[str, FeatureResult]:
        lower, upper = candidate.lower, candidate.upper
        anchors = lower.anchors + upper.anchors
        event_index = max(point.index for point in anchors)
        atr = average_true_range(data[: event_index + 1])[-1]
        errors = [
            abs(point.price - boundary.value_at(point.index))
            for boundary in (lower, upper)
            for point in boundary.anchors
        ]
        fit_error = sum(errors) / len(errors)
        width = upper.intercept - lower.intercept
        values = {
            "lower_anchor_count": float(len(lower.anchors)),
            "upper_anchor_count": float(len(upper.anchors)),
            "channel_span": float(candidate.end_index - candidate.start_index),
            "line_slope": lower.slope,
            "slope_difference": 0.0,
            "slope_difference_atr": 0.0,
            "channel_width": width,
            "channel_width_atr": width / atr if atr > 0.0 else 0.0,
            "fit_error": fit_error,
            "fit_error_atr": fit_error / atr if atr > 0.0 else 0.0,
            "anchor_balance": min(len(lower.anchors), len(upper.anchors))
            / max(len(lower.anchors), len(upper.anchors)),
            "body_violation_count": float(candidate.body_violation_count),
            "wick_breach_count": float(candidate.wick_breach_count),
        }
        return {name: FeatureResult(name, value, 1.0) for name, value in values.items()}

    @staticmethod
    def _raw_points(points: Sequence[Pivot]) -> list[tuple[int, float]]:
        return [(point.index, point.price) for point in points]

    @staticmethod
    def _line_points(boundary: ChannelBoundary) -> list[tuple[int, float]]:
        return [(point.index, boundary.value_at(point.index)) for point in boundary.anchors]

    @staticmethod
    def _line_geometry(
        boundary: ChannelBoundary, start: int, end: int
    ) -> Mapping[str, tuple[int, float]]:
        return {
            "start": (start, boundary.value_at(start)),
            "end": (end, boundary.value_at(end)),
        }
