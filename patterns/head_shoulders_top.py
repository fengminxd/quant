"""Head-and-shoulders top built on the shared mirrored structure engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import HeadAndShouldersTopScore
from indicators.swing import PivotDetector
from patterns.inverse_head_shoulders import InverseHeadShoulders


class HeadAndShouldersTop(Pattern):
    """Detect buying exhaustion and a lower right-shoulder rebound."""

    pattern_id = "PATTERN_008"
    name = "Head and Shoulders Top"

    def __init__(
        self,
        pivot_detector: PivotDetector | None = None,
        min_span: int = 40,
        min_leg_span: int = 10,
        min_neckline_leg_span: int = 5,
        min_head_height_atr: float = 0.5,
        max_shoulder_error_atr: float = 1.0,
        max_head_extreme_error_atr: float = 0.1,
        max_breakdown_bars: int = 40,
    ) -> None:
        self.min_span = min_span
        self.factor = HeadAndShouldersTopScore()
        self._engine = InverseHeadShoulders(
            swing_detector=pivot_detector or PivotDetector(left=5, right=5),
            min_span=min_span,
            min_leg_span=min_leg_span,
            min_neckline_leg_span=min_neckline_leg_span,
            min_head_depth_atr=min_head_height_atr,
            max_shoulder_error_atr=max_shoulder_error_atr,
            max_head_extreme_error_atr=max_head_extreme_error_atr,
            max_breakout_bars=max_breakdown_bars,
        )

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the best confirmed three-swing-high top structure."""

        mirrored = self._engine.detect(self._mirror_bars(data))
        if not mirrored.detected:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._top_features(mirrored.features)
        geometry = self._top_geometry(mirrored.geometry)
        breakdown_confirmed = features["breakdown_confirmed"].value > 0.0
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            self.calculate_score(features),
            features,
            geometry,
            metadata={
                "rule": "confirmed_three_swing_high_head_shoulders_top",
                "state": "breakdown_confirmed" if breakdown_confirmed else "structure_confirmed",
                "detected_at_index": mirrored.metadata["detected_at_index"],
                "head_confirmed_at_index": mirrored.metadata["head_confirmed_at_index"],
                "breakdown_confirmed_at_index": geometry["breakdown_index"],
                "timestamp_semantics": "bar_open_time",
                "timeframe": mirrored.metadata["timeframe"],
                "min_span_bars": self.min_span,
                "left_shoulder_index": mirrored.metadata["left_shoulder_index"],
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract mirrored top features without emitting a trade direction."""

        return self.detect(data).features

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Map top structure and breakdown confirmation to a score."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable shoulder, head, neckline, and breakdown geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    @staticmethod
    def _mirror_bars(data: Sequence[Bar]) -> list[Bar]:
        return [
            Bar(
                timestamp=bar.timestamp,
                open=-bar.open,
                high=-bar.low,
                low=-bar.high,
                close=-bar.close,
                volume=bar.volume,
                timeframe=bar.timeframe,
            )
            for bar in data
        ]

    @staticmethod
    def _top_features(
        mirrored: Mapping[str, FeatureResult],
    ) -> Mapping[str, FeatureResult]:
        mapping = {
            "head_depth_atr": "head_height_atr",
            "prior_decline_atr": "prior_advance_atr",
            "breakout_confirmed": "breakdown_confirmed",
            "breakout_distance_atr": "breakdown_distance_atr",
            "breakout_volume_ratio": "breakdown_volume_ratio",
        }
        features: dict[str, FeatureResult] = {}
        for source, result in mirrored.items():
            target = mapping.get(source, source)
            value = result.value
            if source == "neckline_slope_atr_per_bar":
                value = -value
            features[target] = FeatureResult(target, value, result.confidence, result.metadata)
        return features

    @staticmethod
    def _top_geometry(geometry: Mapping[str, object]) -> Mapping[str, object]:
        points = geometry.get("points", [])
        neckline = geometry.get("neckline_points", [])
        return {
            "points": [(index, -price) for index, price in points],
            "point_timestamps": geometry.get("point_timestamps", []),
            "neckline_points": [(index, -price) for index, price in neckline],
            "neckline_timestamps": geometry.get("neckline_timestamps", []),
            "breakdown_index": geometry.get("breakout_index"),
            "breakdown_timestamp": geometry.get("breakout_timestamp"),
        }
