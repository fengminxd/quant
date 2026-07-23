"""Features for the eight fixed high-priority price-action combinations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.models import Bar, FeatureResult, PatternResult
from core.timeframes import TRADING_TIMEFRAMES
from features.context import ContextFeatureExtractor, directional_structure_score
from features.priority_level_context import (
    PriorLevelMatch,
    PriorityLevelContextMatcher,
)
from features.priority_profiles import (
    PriorityCombinationFeatureSet,
    priority_profile,
)
from indicators.ema import exponential_moving_average


class PriorityCombinationFeatureExtractor:
    """Extract same-timeframe EMA, level-lineage, and trend-gate evidence."""

    def __init__(
        self,
        level_matcher: PriorityLevelContextMatcher | None = None,
        ema_period: int = 99,
        trend_lookback: int = 20,
    ) -> None:
        if ema_period <= 0 or trend_lookback <= 0:
            raise ValueError("periods must be positive")
        self.level_matcher = level_matcher or PriorityLevelContextMatcher()
        self.ema_period = ema_period
        self.trend_lookback = trend_lookback

    def extract(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        *,
        as_of_index: int | None = None,
        window_start_index: int | None = None,
    ) -> PriorityCombinationFeatureSet | None:
        """Return a configured combination using bars visible at ``as_of_index``."""
        if not data:
            raise ValueError("at least one bar is required")
        as_of = len(data) - 1 if as_of_index is None else as_of_index
        if not 0 <= as_of < len(data):
            raise ValueError("as_of_index is outside supplied data")
        offset = self._window_offset(pattern, window_start_index)
        groups = self._absolute_groups(pattern, offset)
        profile = priority_profile(pattern, groups)
        if profile is None:
            return None
        combination_id, name, conditions = profile
        visible = data[: as_of + 1]
        timeframe = visible[-1].timeframe
        features: dict[str, FeatureResult] = {
            "pattern_gate": self._flag(
                "pattern_gate", pattern.detected, float(pattern.detected)
            ),
            "timeframe_gate": self._flag(
                "timeframe_gate",
                timeframe in TRADING_TIMEFRAMES,
                1.0,
                {"timeframe": timeframe, "allowed": TRADING_TIMEFRAMES},
            ),
            "variant_gate": self._variant_gate(pattern, combination_id),
            "trend_gate": self._flag("trend_gate", True, 1.0),
            "pattern_quality": FeatureResult(
                "pattern_quality", pattern.score, float(pattern.detected)
            ),
        }
        ema = exponential_moving_average(visible, self.ema_period)
        self._populate_conditions(
            features, combination_id, conditions, groups, visible, as_of, ema
        )
        return PriorityCombinationFeatureSet(combination_id, name, conditions, features)

    def _populate_conditions(
        self,
        features: dict[str, FeatureResult],
        combination_id: str,
        conditions: tuple[str, ...],
        groups: Mapping[str, tuple[int, ...]],
        data: Sequence[Bar],
        as_of: int,
        ema: Sequence[float],
    ) -> None:
        points = groups.get("points", ())
        upper = groups.get("upper_points", ())
        lower = groups.get("lower_points", ())
        if combination_id == "FIXED_COMBO_001":
            features[conditions[0]] = self._ema_condition(
                data, ema, points[1], "close", above=True, name=conditions[0]
            )
        elif combination_id == "FIXED_COMBO_002":
            features[conditions[0]] = self._ema_condition(
                data, ema, points[1], "open", above=False, name=conditions[0]
            )
        elif combination_id == "FIXED_COMBO_003":
            features[conditions[0]] = self._ema_condition(
                data, ema, points[1], "close", above=True, name=conditions[0]
            )
            features[conditions[1]] = self._level_feature(
                conditions[1],
                self.level_matcher.double_bottom(data, points[1], as_of),
            )
        elif combination_id == "FIXED_COMBO_004":
            features[conditions[0]] = self._ema_condition(
                data, ema, points[1], "open", above=False, name=conditions[0]
            )
            features[conditions[1]] = self._level_feature(
                conditions[1],
                self.level_matcher.horizontal_resistance(data, points[1], as_of),
            )
        elif combination_id == "FIXED_COMBO_005":
            features[conditions[0]] = self._level_feature(
                conditions[0],
                self.level_matcher.double_bottom(data, points[0], as_of),
            )
            features[conditions[1]] = self._all_ema_condition(
                data, ema, points, "close", above=True, name=conditions[1]
            )
            features[conditions[2]] = self._level_feature(
                conditions[2],
                self.level_matcher.breakout_retest_support(data, points[2], as_of),
            )
        elif combination_id == "FIXED_COMBO_006":
            features[conditions[0]] = self._level_feature(
                conditions[0],
                self.level_matcher.horizontal_resistance(data, points[0], as_of),
            )
            features[conditions[1]] = self._ema_condition(
                data, ema, points[2], "open", above=False, name=conditions[1]
            )
        elif combination_id == "FIXED_COMBO_007":
            features["trend_gate"] = self._trend_gate(data, min((*upper, *lower)), True)
            features[conditions[0]] = self._level_feature(
                conditions[0],
                self.level_matcher.double_bottom(data, lower[0], as_of),
            )
            features[conditions[1]] = self._ema_condition(
                data, ema, lower[2], "close", above=True, name=conditions[1]
            )
        elif combination_id == "FIXED_COMBO_008":
            features["trend_gate"] = self._trend_gate(data, min((*upper, *lower)), False)
            features[conditions[0]] = self._level_feature(
                conditions[0],
                self.level_matcher.horizontal_resistance(data, upper[0], as_of),
            )
            features[conditions[1]] = self._ema_condition(
                data, ema, upper[2], "open", above=False, name=conditions[1]
            )

    def _trend_gate(
        self, data: Sequence[Bar], first_anchor: int, bullish: bool
    ) -> FeatureResult:
        prior = data[: first_anchor + 1]
        extracted = ContextFeatureExtractor(
            ema_period=self.ema_period,
            trend_lookback=self.trend_lookback,
        ).extract(prior)
        score, confidence, active = directional_structure_score(
            extracted, bullish=bullish
        )
        return self._flag(
            "trend_gate",
            active,
            confidence,
            {
                "direction": "uptrend" if bullish else "downtrend",
                "trend_score": round(score, 4),
                "frozen_at_index": first_anchor,
            },
        )

    def _ema_condition(
        self,
        data: Sequence[Bar],
        ema: Sequence[float],
        index: int,
        field: str,
        *,
        above: bool,
        name: str,
    ) -> FeatureResult:
        if not 0 <= index < len(data):
            raise ValueError("pattern anchor is outside supplied data")
        value = float(getattr(data[index], field))
        warmed = index + 1 >= self.ema_period
        matched = warmed and (value > ema[index] if above else value < ema[index])
        shadow_cross = (
            data[index].low < ema[index]
            if above
            else data[index].high > ema[index]
        )
        return self._flag(
            name,
            matched,
            1.0 if warmed else 0.0,
            {
                "anchor_index": index,
                "price_field": field,
                "price": value,
                "ema99": ema[index],
                "distance": value - ema[index],
                "shadow_crossed_ema99": shadow_cross,
                "ema_period": self.ema_period,
            },
        )

    def _all_ema_condition(
        self,
        data: Sequence[Bar],
        ema: Sequence[float],
        indexes: Sequence[int],
        field: str,
        *,
        above: bool,
        name: str,
    ) -> FeatureResult:
        checks = [
            self._ema_condition(
                data, ema, index, field, above=above, name=f"{name}_{position}"
            )
            for position, index in enumerate(indexes, start=1)
        ]
        return self._flag(
            name,
            all(check.value == 1.0 for check in checks),
            min(check.confidence for check in checks),
            {"anchors": tuple(check.metadata for check in checks)},
        )

    @staticmethod
    def _level_feature(name: str, match: PriorLevelMatch) -> FeatureResult:
        return FeatureResult(
            name,
            float(match.matched),
            1.0,
            {
                "rule_type": match.rule_type,
                "source_index": match.source_index,
                "target_index": match.target_index,
                "level": match.level,
                "level_error": match.level_error,
                "breakout_index": match.breakout_index,
                "contact_overlap": match.contact_overlap,
            },
        )

    @staticmethod
    def _variant_gate(pattern: PatternResult, combination_id: str) -> FeatureResult:
        required = "double_swing_low" if combination_id == "FIXED_COMBO_001" else None
        actual = pattern.metadata.get("rule_type")
        passed = required is None or actual == required
        return PriorityCombinationFeatureExtractor._flag(
            "variant_gate",
            passed,
            1.0,
            {"required_rule_type": required, "actual_rule_type": actual},
        )

    @staticmethod
    def _window_offset(
        pattern: PatternResult, explicit: int | None
    ) -> int:
        value = pattern.metadata.get("window_start_index", 0) if explicit is None else explicit
        if not isinstance(value, int) or value < 0:
            raise ValueError("window_start_index must be a non-negative integer")
        return value

    @staticmethod
    def _absolute_groups(
        pattern: PatternResult, offset: int
    ) -> Mapping[str, tuple[int, ...]]:
        groups: dict[str, tuple[int, ...]] = {}
        for name in ("points", "upper_points", "lower_points"):
            raw = pattern.geometry.get(name, ())
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                groups[name] = tuple(
                    int(point[0]) + offset
                    for point in raw
                    if isinstance(point, Sequence)
                    and not isinstance(point, (str, bytes))
                    and point
                )
        return groups

    @staticmethod
    def _flag(
        name: str,
        matched: bool,
        confidence: float,
        metadata: Mapping[str, object] | None = None,
    ) -> FeatureResult:
        return FeatureResult(name, float(matched), confidence, dict(metadata or {}))
