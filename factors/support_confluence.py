"""Event-anchored scoring for bullish slope/horizontal support confluence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.base import Factor
from core.models import Bar, FactorResult, FeatureResult, PatternResult
from factors.context_factors import EMA99ContextScore
from features.basic import clamp
from features.context import ContextFeatureExtractor
from indicators.atr import average_true_range
from patterns.horizontal_support import HorizontalSupport
from patterns.three_point_trendline_support import ThreePointTrendlineSupport


@dataclass(frozen=True)
class SupportConfluenceEvaluation:
    """Two support patterns and their event-time 0-100 factor score."""

    trendline: PatternResult
    horizontal: PatternResult
    factor: FactorResult


class BullishSupportConfluenceScore(Factor):
    """Score a shared-anchor slope support and resistance-retest confluence."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return high scores only when all non-directional evidence gates pass."""

        trendline = _value(features, "trendline_quality")
        horizontal = _value(features, "horizontal_quality")
        shared = _value(features, "shared_anchor") >= 1.0
        reclaim_distance = _value(features, "resistance_reclaim_distance_atr")
        above_ema = _value(features, "event_close_above_ema99") >= 1.0
        ema = EMA99ContextScore().calculate(features)
        gate_passed = (
            trendline > 0.0
            and horizontal > 0.0
            and shared
            and reclaim_distance > 0.0
            and above_ema
            and bool(ema.metadata.get("active", False))
        )
        if not gate_passed:
            return FactorResult(
                "BullishSupportConfluenceScore",
                0.0,
                _values(features),
                {"active": False, "gate_passed": False},
            )
        reclaim_score = clamp(50.0 + reclaim_distance * 50.0)
        score = clamp(
            0.30 * trendline
            + 0.25 * horizontal
            + 0.25 * reclaim_score
            + 0.20 * ema.score
        )
        return FactorResult(
            "BullishSupportConfluenceScore",
            round(score, 4),
            _values(features),
            {
                "active": True,
                "gate_passed": True,
                "components": {
                    "trendline_quality": round(trendline, 4),
                    "horizontal_quality": round(horizontal, 4),
                    "resistance_reclaim": round(reclaim_score, 4),
                    "ema99_context": ema.score,
                },
                "weights": {
                    "trendline_quality": 0.30,
                    "horizontal_quality": 0.25,
                    "resistance_reclaim": 0.25,
                    "ema99_context": 0.20,
                },
                "confirmation_lag_bars": int(
                    _value(features, "confirmation_lag_bars")
                ),
                "signal_semantics": "score_only",
            },
        )


class SupportConfluenceScorer:
    """Detect and score support confluence at a confirmed third-point event."""

    def __init__(
        self,
        trendline: ThreePointTrendlineSupport | None = None,
        horizontal: HorizontalSupport | None = None,
        extractor: ContextFeatureExtractor | None = None,
    ) -> None:
        self.trendline = trendline or ThreePointTrendlineSupport()
        self.horizontal = horizontal or HorizontalSupport(
            swing_detector=self.trendline.swing_detector
        )
        self.extractor = extractor or ContextFeatureExtractor(
            swing_detector=self.trendline.swing_detector
        )
        self.factor = BullishSupportConfluenceScore()

    def evaluate(
        self,
        data: Sequence[Bar],
        event_index: int,
        as_of_index: int | None = None,
    ) -> SupportConfluenceEvaluation:
        """Use confirmation bars for detection and event-close bars for factors."""

        if not data:
            raise ValueError("at least one bar is required")
        as_of = len(data) - 1 if as_of_index is None else as_of_index
        if event_index < 0 or event_index >= len(data):
            raise ValueError("event_index is outside supplied data")
        if as_of < event_index or as_of >= len(data):
            raise ValueError("as_of_index must include the event and supplied data")
        visible = data[: as_of + 1]
        trendline = self.trendline.detect_at(visible, event_index)
        horizontal = self.horizontal.detect_at(visible, event_index)
        features = self._features(data, event_index, trendline, horizontal)
        factor = self.factor.calculate(features)
        metadata = dict(factor.metadata)
        metadata.update(
            {
                "event_index": event_index,
                "as_of_index": as_of,
                "event_timestamp": data[event_index].timestamp,
                "detected_at_index": max(
                    _detected_at(trendline), _detected_at(horizontal)
                ),
            }
        )
        factor = FactorResult(factor.name, factor.score, factor.features, metadata)
        return SupportConfluenceEvaluation(trendline, horizontal, factor)

    def _features(
        self,
        data: Sequence[Bar],
        event_index: int,
        trendline: PatternResult,
        horizontal: PatternResult,
    ) -> Mapping[str, FeatureResult]:
        event_window = data[: event_index + 1]
        context = dict(self.extractor.extract(event_window))
        shared = _right_anchor(trendline) == event_index == _right_anchor(horizontal)
        level = float(horizontal.geometry.get("level", data[event_index].close))
        atr = max(average_true_range(event_window)[-1], 1e-12)
        ema = context["ema99_value"]
        confirmation = max(_detected_at(trendline), _detected_at(horizontal))
        context.update(
            {
                "trendline_quality": FeatureResult(
                    "trendline_quality", trendline.score, float(trendline.detected)
                ),
                "horizontal_quality": FeatureResult(
                    "horizontal_quality", horizontal.score, float(horizontal.detected)
                ),
                "shared_anchor": FeatureResult(
                    "shared_anchor",
                    float(shared),
                    float(trendline.detected and horizontal.detected),
                ),
                "resistance_reclaim_distance_atr": FeatureResult(
                    "resistance_reclaim_distance_atr",
                    (data[event_index].close - level) / atr,
                    float(horizontal.detected),
                ),
                "event_close_above_ema99": FeatureResult(
                    "event_close_above_ema99",
                    float(data[event_index].close > ema.value),
                    ema.confidence,
                ),
                "confirmation_lag_bars": FeatureResult(
                    "confirmation_lag_bars",
                    float(max(0, confirmation - event_index)),
                    1.0,
                ),
            }
        )
        return context


def _right_anchor(result: PatternResult) -> int:
    points = result.geometry.get("points", ())
    return int(points[-1][0]) if result.detected and points else -1


def _detected_at(result: PatternResult) -> int:
    value = result.metadata.get("detected_at_index", -1)
    return int(value) if isinstance(value, int) else -1


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].value if name in features else 0.0


def _values(features: Mapping[str, FeatureResult]) -> Mapping[str, float]:
    return {name: result.value for name, result in features.items()}
