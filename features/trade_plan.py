"""Causal default trade plans derived after pattern detection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from core.models import Bar, PatternResult
from core.pattern_policy import is_trading_pattern_enabled
from features.entry_retest import (
    EntryRetestAssessment,
    EntryRetestFeatureExtractor,
)
from indicators.atr import average_true_range
from indicators.swing import SwingDetector

TradeDirection = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class PatternTradePlan:
    """One explicit entry, structural stop, and price-action target."""

    direction: TradeDirection
    entry_price: float
    stop_price: float
    target_price: float
    target_source: str = "explicit"
    entry_index: int | None = None
    entry_source: str = "explicit"
    structure_level: float | None = None
    entry_distance_atr: float | None = None


class PatternTradePlanExtractor:
    """Build a causal default trade plan from standard pattern geometry."""

    def __init__(
        self,
        stop_buffer_atr: float = 0.20,
        swing_detector: SwingDetector | None = None,
        entry_extractor: EntryRetestFeatureExtractor | None = None,
    ) -> None:
        if stop_buffer_atr < 0.0:
            raise ValueError("stop_buffer_atr must be non-negative")
        self.stop_buffer_atr = stop_buffer_atr
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.entry_extractor = entry_extractor or EntryRetestFeatureExtractor()

    def extract(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        as_of_index: int | None = None,
        plan: PatternTradePlan | None = None,
        entry_assessment: EntryRetestAssessment | None = None,
    ) -> tuple[PatternTradePlan | None, int, float]:
        """Return a plan using no bars later than ``as_of_index``."""

        if not data:
            raise ValueError("at least one bar is required")
        index = len(data) - 1 if as_of_index is None else as_of_index
        if index < 0 or index >= len(data):
            raise ValueError("as_of_index is outside supplied data")
        self._validate_visible(pattern, index)
        window = data[: index + 1]
        if (
            not pattern.detected
            or not is_trading_pattern_enabled(pattern.pattern_id)
            or data[index].timeframe == "1d"
        ):
            atr = max(average_true_range(window)[-1], 1e-12)
            return None, index, atr
        atr = max(average_true_range(window)[-1], 1e-12)
        if plan is not None:
            direction = self._fixed_direction(pattern)
            if pattern.pattern_id == "PATTERN_002":
                assessment = self.entry_extractor.extract(pattern, window, index, atr)
                direction = assessment.direction
                if direction is None:
                    return None, index, atr
            direction = direction or plan.direction
            if plan.direction != direction:
                raise ValueError("explicit plan direction conflicts with pattern direction")
            resolved = plan if plan.entry_index is not None else replace(
                plan, entry_index=index
            )
            return resolved, index, atr
        assessment = entry_assessment or self.entry_extractor.extract(
            pattern, window, index, atr
        )
        direction = assessment.direction
        if not assessment.eligible or direction is None:
            return None, index, atr
        extracted = self._default_plan(
            pattern,
            window,
            index,
            atr,
            direction,
            assessment,
        )
        if extracted is not None and extracted.entry_index is None:
            distance = assessment.features.get("entry_distance_atr")
            extracted = replace(
                extracted,
                entry_index=index,
                entry_source=assessment.structure_source,
                structure_level=assessment.structure_level,
                entry_distance_atr=distance.value if distance else None,
            )
        return extracted, index, atr

    def _default_plan(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        index: int,
        atr: float,
        direction: TradeDirection,
        assessment: EntryRetestAssessment,
    ) -> PatternTradePlan | None:
        entry = data[index].close
        buffer = atr * self.stop_buffer_atr
        pattern_id = pattern.pattern_id
        if pattern_id in {"PATTERN_001", "PATTERN_003", "PATTERN_005"}:
            line = assessment.structure_level
            target = self._opposing_liquidity(data, index, entry, direction)
            if line is None or target is None:
                return None
            stop = line - buffer if direction == "bullish" else line + buffer
            return PatternTradePlan(
                direction, entry, stop, target, "confirmed_swing_liquidity"
            )
        if pattern_id in {"PATTERN_004", "PATTERN_006"}:
            level = assessment.structure_level
            target = self._opposing_liquidity(data, index, entry, direction)
            if not isinstance(level, (int, float)) or target is None:
                return None
            stop = float(level) - buffer if direction == "bullish" else float(level) + buffer
            return PatternTradePlan(
                direction, entry, stop, target, "confirmed_swing_liquidity"
            )
        if pattern_id == "PATTERN_002":
            return self._triangle_plan(
                pattern, entry, index, buffer, direction, assessment
            )
        if pattern_id in {"PATTERN_007", "PATTERN_008"}:
            return self._head_shoulders_plan(pattern, entry, buffer, direction)
        return None

    def _triangle_plan(
        self,
        pattern: PatternResult,
        entry: float,
        index: int,
        buffer: float,
        direction: TradeDirection,
        assessment: EntryRetestAssessment,
    ) -> PatternTradePlan | None:
        highs = self._points(pattern, "upper_points")
        lows = self._points(pattern, "lower_points")
        if not highs or not lows:
            return None
        upper = self._geometry_line(pattern, "upper_line", index)
        lower = self._geometry_line(pattern, "lower_line", index)
        level = assessment.structure_level
        if upper is None or lower is None or level is None or upper <= lower:
            return None
        if direction == "bullish":
            if upper <= entry:
                return None
            return PatternTradePlan(
                direction, entry, level - buffer, upper,
                "triangle_opposite_boundary",
            )
        if lower >= entry:
            return None
        return PatternTradePlan(
            direction, entry, level + buffer, lower,
            "triangle_opposite_boundary",
        )

    def _head_shoulders_plan(
        self,
        pattern: PatternResult,
        entry: float,
        buffer: float,
        direction: TradeDirection,
    ) -> PatternTradePlan | None:
        points = self._points(pattern, "points")
        neckline = self._points(pattern, "neckline_points")
        if len(points) != 3 or len(neckline) != 2:
            return None
        head_index, head_price = points[1]
        neck_at_head = _line_value(neckline[0], neckline[1], head_index)
        right_price = points[2][1]
        height = abs(neck_at_head - head_price)
        if direction == "bullish":
            return PatternTradePlan(
                direction, entry, right_price - buffer, entry + height,
                "head_neckline_measured_move",
            )
        return PatternTradePlan(
            direction, entry, right_price + buffer, entry - height,
            "head_neckline_measured_move",
        )

    def _opposing_liquidity(
        self,
        data: Sequence[Bar],
        index: int,
        entry: float,
        direction: TradeDirection,
    ) -> float | None:
        pivots = self.swing_detector.detect(data[: index + 1])
        if direction == "bullish":
            prices = [
                point.price
                for point in pivots
                if point.kind == "high" and point.price > entry
            ]
            return min(prices) if prices else None
        prices = [
            point.price for point in pivots if point.kind == "low" and point.price < entry
        ]
        return max(prices) if prices else None

    def _geometry_line(
        self, pattern: PatternResult, name: str, index: int
    ) -> float | None:
        geometry = pattern.geometry.get(name)
        if not isinstance(geometry, Mapping):
            return None
        start = self._point(pattern, geometry.get("start"))
        end = self._point(pattern, geometry.get("end"))
        return _line_value(start, end, index) if start and end else None

    def _points(self, pattern: PatternResult, name: str) -> list[tuple[int, float]]:
        raw = pattern.geometry.get(name, ())
        if not isinstance(raw, (list, tuple)):
            return []
        return [
            point for item in raw if (point := self._point(pattern, item)) is not None
        ]

    @staticmethod
    def _point(pattern: PatternResult, value: object) -> tuple[int, float] | None:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        if not isinstance(value[0], (int, float)) or not isinstance(value[1], (int, float)):
            return None
        offset = pattern.metadata.get("window_start_index", 0)
        global_offset = int(offset) if isinstance(offset, (int, float)) else 0
        return int(value[0]) + global_offset, float(value[1])

    @staticmethod
    def _fixed_direction(pattern: PatternResult) -> TradeDirection | None:
        fixed: Mapping[str, TradeDirection] = {
            "PATTERN_001": "bullish", "PATTERN_003": "bullish",
            "PATTERN_004": "bullish", "PATTERN_005": "bearish",
            "PATTERN_006": "bearish", "PATTERN_007": "bullish",
            "PATTERN_008": "bearish",
        }
        return fixed.get(pattern.pattern_id)

    @staticmethod
    def _validate_visible(pattern: PatternResult, as_of_index: int) -> None:
        detected_at = pattern.metadata.get("detected_at_index")
        offset = pattern.metadata.get("window_start_index", 0)
        if isinstance(detected_at, int):
            global_offset = int(offset) if isinstance(offset, (int, float)) else 0
            if detected_at + global_offset > as_of_index:
                raise ValueError("as_of_index precedes pattern confirmation")


def _line_value(left: tuple[int, float], right: tuple[int, float], index: int) -> float:
    if right[0] == left[0]:
        return right[1]
    slope = (right[1] - left[1]) / (right[0] - left[0])
    return left[1] + slope * (index - left[0])
