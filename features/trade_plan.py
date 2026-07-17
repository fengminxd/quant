"""Causal default trade plans derived after pattern detection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from core.models import Bar, PatternResult
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


class PatternTradePlanExtractor:
    """Build a causal default trade plan from standard pattern geometry."""

    def __init__(
        self,
        stop_buffer_atr: float = 0.20,
        swing_detector: SwingDetector | None = None,
    ) -> None:
        if stop_buffer_atr < 0.0:
            raise ValueError("stop_buffer_atr must be non-negative")
        self.stop_buffer_atr = stop_buffer_atr
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)

    def extract(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        as_of_index: int | None = None,
        plan: PatternTradePlan | None = None,
        direction_override: TradeDirection | None = None,
        entry_index: int | None = None,
        triangle_entry_mode: str | None = None,
    ) -> tuple[PatternTradePlan | None, int, float]:
        """Return a plan using no bars later than ``as_of_index``."""

        if not data:
            raise ValueError("at least one bar is required")
        index = len(data) - 1 if as_of_index is None else as_of_index
        if index < 0 or index >= len(data):
            raise ValueError("as_of_index is outside supplied data")
        self._validate_visible(pattern, index)
        window = data[: index + 1]
        if not pattern.detected or data[index].timeframe == "1d":
            atr = max(average_true_range(window)[-1], 1e-12)
            return None, index, atr
        direction = self._confirmed_direction(pattern)
        if direction_override is not None:
            if direction is not None and direction != direction_override:
                raise ValueError("direction override conflicts with pattern direction")
            if direction is None and pattern.pattern_id != "PATTERN_002":
                raise ValueError("direction override is only allowed for triangles")
            direction = direction_override
        if direction is None:
            atr = max(average_true_range(window)[-1], 1e-12)
            return None, index, atr
        trade_index = index if entry_index is None else entry_index
        if trade_index < 0 or trade_index > index:
            raise ValueError("entry_index must be visible at as_of_index")
        atr = max(average_true_range(data[: trade_index + 1])[-1], 1e-12)
        if plan is not None:
            if plan.direction != direction:
                raise ValueError("explicit plan direction conflicts with pattern direction")
            resolved = plan if plan.entry_index is not None else replace(
                plan, entry_index=trade_index
            )
            return resolved, index, atr
        extracted = self._default_plan(
            pattern,
            window,
            trade_index,
            atr,
            direction,
            triangle_entry_mode,
        )
        if extracted is not None and extracted.entry_index is None:
            extracted = replace(extracted, entry_index=trade_index)
        return extracted, index, atr

    def _default_plan(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        index: int,
        atr: float,
        direction: TradeDirection,
        triangle_entry_mode: str | None,
    ) -> PatternTradePlan | None:
        entry = data[index].close
        buffer = atr * self.stop_buffer_atr
        pattern_id = pattern.pattern_id
        if pattern_id in {"PATTERN_001", "PATTERN_003", "PATTERN_005"}:
            line = self._projected_line(pattern, index)
            target = self._opposing_liquidity(data, index, entry, direction)
            if line is None or target is None:
                return None
            stop = line - buffer if direction == "bullish" else line + buffer
            return PatternTradePlan(
                direction, entry, stop, target, "confirmed_swing_liquidity"
            )
        if pattern_id in {"PATTERN_004", "PATTERN_006"}:
            level = pattern.geometry.get("level")
            target = self._opposing_liquidity(data, index, entry, direction)
            if not isinstance(level, (int, float)) or target is None:
                return None
            stop = float(level) - buffer if direction == "bullish" else float(level) + buffer
            return PatternTradePlan(
                direction, entry, stop, target, "confirmed_swing_liquidity"
            )
        if pattern_id == "PATTERN_002":
            return self._triangle_plan(
                pattern, entry, index, buffer, direction, triangle_entry_mode
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
        entry_mode: str | None,
    ) -> PatternTradePlan | None:
        highs = self._points(pattern, "upper_points")
        lows = self._points(pattern, "lower_points")
        if not highs or not lows:
            return None
        overlap_start = max(highs[0][0], lows[0][0])
        upper = self._geometry_line(pattern, "upper_line", index)
        lower = self._geometry_line(pattern, "lower_line", index)
        upper_start = self._geometry_line(pattern, "upper_line", overlap_start)
        lower_start = self._geometry_line(pattern, "lower_line", overlap_start)
        if None in {upper, lower, upper_start, lower_start}:
            return None
        height = float(upper_start) - float(lower_start)
        if height <= 0.0:
            return None
        if direction == "bearish" and entry_mode == "upper_boundary_ema_rejection":
            stop = max(float(upper), highs[-1][1]) + buffer
            return PatternTradePlan(
                direction,
                entry,
                stop,
                float(lower),
                "triangle_opposite_boundary",
                index,
            )
        if direction == "bullish":
            return PatternTradePlan(
                direction, entry, upper - buffer, entry + height,
                "triangle_measured_move", index,
            )
        return PatternTradePlan(
            direction, entry, lower + buffer, entry - height,
            "triangle_measured_move", index,
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

    def _projected_line(self, pattern: PatternResult, index: int) -> float | None:
        line = self._geometry_line(pattern, "line", index)
        if line is not None:
            return line
        points = self._points(pattern, "points")
        return _line_value(points[0], points[-1], index) if len(points) >= 2 else None

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
    def _confirmed_direction(pattern: PatternResult) -> TradeDirection | None:
        fixed: Mapping[str, TradeDirection] = {
            "PATTERN_001": "bullish", "PATTERN_003": "bullish",
            "PATTERN_004": "bullish", "PATTERN_005": "bearish",
            "PATTERN_006": "bearish",
        }
        if pattern.pattern_id in fixed:
            return fixed[pattern.pattern_id]
        if pattern.pattern_id == "PATTERN_002":
            breakout = pattern.metadata.get("breakout_direction")
            if breakout in {"upside", "downside"}:
                return "bullish" if breakout == "upside" else "bearish"
            return None
        state = pattern.metadata.get("state")
        if pattern.pattern_id == "PATTERN_007" and state == "breakout_confirmed":
            return "bullish"
        if pattern.pattern_id == "PATTERN_008" and state == "breakdown_confirmed":
            return "bearish"
        return None

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
