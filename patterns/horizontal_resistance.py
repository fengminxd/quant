"""Strict two-swing horizontal resistance pattern."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from factors.pattern_factors import HorizontalResistanceScore
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector


@dataclass(frozen=True)
class HorizontalResistanceCandidate:
    """A horizontal level contacted by two confirmed swing-high candles."""

    points: tuple[Pivot, Pivot]
    level: float
    contact_types: tuple[str, str]


class HorizontalResistance(Pattern):
    """Detect unpenetrated horizontal resistance across any input timeframe.

    A valid level contacts each anchor at its open or upper shadow. Between the
    anchors no candle may trade or open above the level. Span is measured as
    the difference between candle indexes, so 40 means 40 complete bar
    intervals.
    """

    pattern_id = "PATTERN_006"
    name = "Horizontal Resistance"

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_span: int = 40,
        price_epsilon: float = 1e-9,
    ) -> None:
        if min_span <= 0:
            raise ValueError("min_span must be positive")
        if price_epsilon < 0:
            raise ValueError("price_epsilon must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(min_bars=3)
        self.min_span = min_span
        self.price_epsilon = price_epsilon
        self.factor = HorizontalResistanceScore()

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Return the highest-ranked valid resistance known without look-ahead."""

        candidate = self._best_candidate(data)
        if candidate is None:
            return PatternResult(self.pattern_id, self.name, False, 0.0)
        features = self._features_for_candidate(data, candidate)
        left, right = candidate.points
        return PatternResult(
            self.pattern_id,
            self.name,
            True,
            self.calculate_score(features),
            features,
            geometry={
                "level": candidate.level,
                "points": [
                    (left.index, candidate.level),
                    (right.index, candidate.level),
                ],
                "swing_highs": [(left.index, left.price), (right.index, right.price)],
                "point_timestamps": [
                    data[left.index].timestamp,
                    data[right.index].timestamp,
                ],
            },
            metadata={
                "rule": "strict_two_swing_horizontal_resistance",
                "contact_types": candidate.contact_types,
                "detected_at_index": max(left.confirmed_at, right.confirmed_at),
                "timestamp_semantics": "bar_open_time",
                "timeframe": data[right.index].timeframe,
            },
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract reusable features for the highest-ranked valid level."""

        candidate = self._best_candidate(data)
        return {} if candidate is None else self._features_for_candidate(data, candidate)

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Calculate a score-only factor; detection remains rule based."""

        return self.factor.calculate(features).score

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable horizontal resistance geometry."""

        return {"pattern": self.name, "geometry": result.geometry, "score": result.score}

    def _best_candidate(self, data: Sequence[Bar]) -> HorizontalResistanceCandidate | None:
        highs = self.swing_detector.highs(data)
        candidates: list[HorizontalResistanceCandidate] = []
        for left, right in combinations(highs, 2):
            if right.index - left.index < self.min_span:
                continue
            for level in self._shared_contact_levels(data[left.index], data[right.index]):
                if self._penetration_count(data, left.index, right.index, level) > 0:
                    continue
                if self._open_violation_count(
                    data, left.index, right.index, level
                ) > 0:
                    continue
                candidates.append(
                    HorizontalResistanceCandidate(
                        (left, right),
                        level,
                        (
                            self._contact_type(data[left.index], level),
                            self._contact_type(data[right.index], level),
                        ),
                    )
                )
        if not candidates:
            return None
        return max(candidates, key=self._rank)

    def _shared_contact_levels(self, left: Bar, right: Bar) -> tuple[float, ...]:
        candidates: list[float] = []
        for level in (left.open, right.open):
            if self._anchor_contact(left, level) and self._anchor_contact(right, level):
                candidates.append(level)
        shadow_floor = max(max(left.open, left.close), max(right.open, right.close))
        shadow_ceiling = min(left.high, right.high)
        if shadow_floor <= shadow_ceiling + self.price_epsilon:
            candidates.append(shadow_ceiling)
        return tuple(sorted(set(candidates), reverse=True))

    def _anchor_contact(self, bar: Bar, level: float) -> bool:
        at_open = math.isclose(level, bar.open, abs_tol=self.price_epsilon, rel_tol=1e-9)
        body_high = max(bar.open, bar.close)
        in_upper_shadow = body_high - self.price_epsilon <= level <= bar.high + self.price_epsilon
        return at_open or in_upper_shadow

    def _contact_type(self, bar: Bar, level: float) -> str:
        if math.isclose(level, bar.open, abs_tol=self.price_epsilon, rel_tol=1e-9):
            return "open"
        return "upper_shadow"

    def _penetration_count(
        self, data: Sequence[Bar], left_index: int, right_index: int, level: float
    ) -> int:
        return sum(
            bar.high > level + self.price_epsilon
            for bar in data[left_index + 1 : right_index]
        )

    def _open_violation_count(
        self,
        data: Sequence[Bar],
        left_index: int,
        right_index: int,
        level: float,
    ) -> int:
        return sum(
            bar.open > level + self.price_epsilon
            for bar in data[left_index + 1 : right_index]
        )

    def _features_for_candidate(
        self, data: Sequence[Bar], candidate: HorizontalResistanceCandidate
    ) -> Mapping[str, FeatureResult]:
        left, right = candidate.points
        atr_values = average_true_range(data)
        atr_index = min(max(left.confirmed_at, right.confirmed_at), len(atr_values) - 1)
        atr = max(atr_values[atr_index], self.price_epsilon, 1e-12)
        middle = data[left.index + 1 : right.index]
        max_high = max((bar.high for bar in middle), default=candidate.level)
        max_open = max(
            (bar.open for bar in middle),
            default=min(data[left.index].open, data[right.index].open),
        )
        open_ceiling = candidate.level
        overshoot = sum(max(0.0, point.price - candidate.level) for point in (left, right))
        return {
            "anchor_count": FeatureResult("anchor_count", 2.0, 1.0),
            "span": FeatureResult("span", float(right.index - left.index), 1.0),
            "level": FeatureResult("level", candidate.level, 1.0),
            "anchor_overshoot_atr": FeatureResult(
                "anchor_overshoot_atr", overshoot / atr, 1.0
            ),
            "penetration_count": FeatureResult(
                "penetration_count",
                float(
                    self._penetration_count(
                        data, left.index, right.index, candidate.level
                    )
                ),
                1.0,
            ),
            "open_violation_count": FeatureResult(
                "open_violation_count",
                float(
                    self._open_violation_count(
                        data,
                        left.index,
                        right.index,
                        candidate.level,
                    )
                ),
                1.0,
            ),
            "intermediate_touch_count": FeatureResult(
                "intermediate_touch_count",
                float(
                    sum(
                        math.isclose(
                            bar.high,
                            candidate.level,
                            abs_tol=self.price_epsilon,
                            rel_tol=1e-9,
                        )
                        for bar in middle
                    )
                ),
                1.0,
            ),
            "intermediate_clearance_atr": FeatureResult(
                "intermediate_clearance_atr",
                max(0.0, candidate.level - max_high) / atr,
                1.0,
            ),
            "intermediate_open_margin_atr": FeatureResult(
                "intermediate_open_margin_atr",
                max(0.0, open_ceiling - max_open) / atr,
                1.0,
            ),
            "open_anchor_count": FeatureResult(
                "open_anchor_count",
                float(candidate.contact_types.count("open")),
                1.0,
            ),
            "upper_shadow_anchor_count": FeatureResult(
                "upper_shadow_anchor_count",
                float(candidate.contact_types.count("upper_shadow")),
                1.0,
            ),
            "confirmation_lag": FeatureResult(
                "confirmation_lag",
                float(max(left.confirmed_at, right.confirmed_at) - right.index),
                1.0,
            ),
        }

    @staticmethod
    def _rank(
        candidate: HorizontalResistanceCandidate,
    ) -> tuple[float, float, float]:
        left, right = candidate.points
        overshoot = sum(point.price - candidate.level for point in candidate.points)
        return (float(right.index - left.index), -overshoot, float(right.index))
