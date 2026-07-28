"""Causal structure-zone retest and reclaim entry features."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Bar, FeatureResult, PatternResult
from features.context import ContextFeatureExtractor, directional_structure_score

EntryDirection = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class EntryRetestAssessment:
    """Observable entry setup at one candle close."""

    direction: EntryDirection | None
    structure_level: float | None
    structure_source: str
    anchor_index: int | None
    features: Mapping[str, FeatureResult]

    @property
    def eligible(self) -> bool:
        """Whether the bar completed the configured retest/reclaim gate."""

        feature = self.features.get("entry_gate_passed")
        return feature is not None and feature.value == 1.0


class EntryRetestFeatureExtractor:
    """Resolve pattern-specific structure and test a causal reclaim."""

    def __init__(
        self,
        zone_width_atr: float = 0.25,
        max_close_distance_atr: float = 0.35,
        max_wait_bars: int = 11,
        context_extractor: ContextFeatureExtractor | None = None,
    ) -> None:
        if zone_width_atr <= 0.0 or max_close_distance_atr <= 0.0:
            raise ValueError("entry distances must be positive")
        if max_wait_bars < 0:
            raise ValueError("max_wait_bars must be non-negative")
        self.zone_width_atr = zone_width_atr
        self.max_close_distance_atr = max_close_distance_atr
        self.max_wait_bars = max_wait_bars
        self.context_extractor = context_extractor or ContextFeatureExtractor()

    def extract(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        index: int,
        atr: float,
    ) -> EntryRetestAssessment:
        """Return features using only ``data[:index + 1]``."""

        if index < 0 or index >= len(data):
            raise ValueError("index is outside supplied data")
        if not pattern.detected:
            return self._unavailable("pattern_not_detected")
        setup = self._setup(pattern, data, index)
        if setup is None:
            return self._unavailable("structure_unavailable")
        direction, level, source, anchor_index, trend_score, trend_confidence = setup
        detected_at = _global_index(pattern, "detected_at_index", index)
        age = index - detected_at
        bar = data[index]
        zone = atr * self.zone_width_atr
        overlaps = bar.low <= level + zone and bar.high >= level - zone
        reclaimed = bar.close >= level if direction == "bullish" else bar.close <= level
        distance_atr = abs(bar.close - level) / atr
        fresh = 1 <= age <= self.max_wait_bars
        visible_anchor = anchor_index is None or anchor_index <= index
        gate = (
            overlaps
            and reclaimed
            and distance_atr <= self.max_close_distance_atr
            and fresh
            and visible_anchor
        )
        confidence = min(1.0, max(0.0, trend_confidence))
        features = {
            "entry_gate_passed": _feature("entry_gate_passed", gate, confidence),
            "structure_retest": _feature("structure_retest", overlaps, confidence),
            "structure_reclaimed": _feature(
                "structure_reclaimed", reclaimed, confidence
            ),
            "entry_distance_atr": _feature(
                "entry_distance_atr", distance_atr, confidence
            ),
            "entry_zone_width_atr": _feature(
                "entry_zone_width_atr", self.zone_width_atr, 1.0
            ),
            "max_close_distance_atr": _feature(
                "max_close_distance_atr", self.max_close_distance_atr, 1.0
            ),
            "bars_since_detection": _feature(
                "bars_since_detection", float(age), 1.0
            ),
            "max_wait_bars": _feature(
                "max_wait_bars", float(self.max_wait_bars), 1.0
            ),
            "entry_wait_fresh": _feature("entry_wait_fresh", fresh, 1.0),
            "prior_trend_score": _feature(
                "prior_trend_score", trend_score, confidence
            ),
            "structure_level": FeatureResult(
                "structure_level",
                level,
                confidence,
                {
                    "direction": direction,
                    "source": source,
                    "anchor_index": anchor_index,
                },
            ),
        }
        return EntryRetestAssessment(
            direction, level, source, anchor_index, features
        )

    def _setup(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        index: int,
    ) -> tuple[EntryDirection, float, str, int | None, float, float] | None:
        pattern_id = pattern.pattern_id
        if pattern_id in {"PATTERN_001", "PATTERN_003", "PATTERN_005"}:
            points = _points(pattern, "points")
            line = _geometry_line(pattern, "line", index)
            if line is None and len(points) >= 2:
                line = _line_value(points[0], points[-1], index)
            if line is None:
                return None
            direction = "bearish" if pattern_id == "PATTERN_005" else "bullish"
            return direction, line, "projected_structure_line", None, 100.0, 1.0
        if pattern_id in {"PATTERN_004", "PATTERN_006"}:
            level = pattern.geometry.get("level")
            if not isinstance(level, (int, float)):
                return None
            direction = "bullish" if pattern_id == "PATTERN_004" else "bearish"
            return direction, float(level), "horizontal_structure", None, 100.0, 1.0
        if pattern_id in {"PATTERN_007", "PATTERN_008"}:
            points = _points(pattern, "points")
            if len(points) != 3:
                return None
            direction = "bullish" if pattern_id == "PATTERN_007" else "bearish"
            return (
                direction,
                points[2][1],
                "right_shoulder_zone",
                points[2][0],
                100.0,
                1.0,
            )
        if pattern_id == "PATTERN_002":
            return self._triangle_setup(pattern, data)
        return None

    def _triangle_setup(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
    ) -> tuple[EntryDirection, float, str, int, float, float] | None:
        upper = _points(pattern, "upper_points")
        lower = _points(pattern, "lower_points")
        if not upper or not lower:
            return None
        first_index = min(upper[0][0], lower[0][0])
        if first_index < 0 or first_index >= len(data):
            return None
        context = self.context_extractor.extract(data[: first_index + 1])
        up_score, up_confidence, up_active = directional_structure_score(
            context, bullish=True
        )
        down_score, down_confidence, down_active = directional_structure_score(
            context, bullish=False
        )
        candidates: list[
            tuple[EntryDirection, float, str, int, float, float]
        ] = []
        if up_active and len(lower) >= 3:
            candidates.append(
                (
                    "bullish",
                    lower[2][1],
                    "triangle_lower_third_anchor",
                    lower[2][0],
                    up_score,
                    up_confidence,
                )
            )
        if down_active and len(upper) >= 3:
            candidates.append(
                (
                    "bearish",
                    upper[2][1],
                    "triangle_upper_third_anchor",
                    upper[2][0],
                    down_score,
                    down_confidence,
                )
            )
        return max(candidates, key=lambda item: item[4]) if candidates else None

    @staticmethod
    def _unavailable(reason: str) -> EntryRetestAssessment:
        feature = FeatureResult(
            "entry_gate_passed", 0.0, 0.0, {"reason": reason}
        )
        return EntryRetestAssessment(
            None, None, reason, None, {"entry_gate_passed": feature}
        )


def _points(pattern: PatternResult, name: str) -> list[tuple[int, float]]:
    raw = pattern.geometry.get(name, ())
    if not isinstance(raw, (list, tuple)):
        return []
    offset = _global_offset(pattern)
    points: list[tuple[int, float]] = []
    for value in raw:
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append((int(value[0]) + offset, float(value[1])))
    return points


def _geometry_line(
    pattern: PatternResult, name: str, index: int
) -> float | None:
    geometry = pattern.geometry.get(name)
    if not isinstance(geometry, Mapping):
        return None
    start = _point(pattern, geometry.get("start"))
    end = _point(pattern, geometry.get("end"))
    return _line_value(start, end, index) if start and end else None


def _point(pattern: PatternResult, value: object) -> tuple[int, float] | None:
    if (
        not isinstance(value, (list, tuple))
        or len(value) < 2
        or not isinstance(value[0], (int, float))
        or not isinstance(value[1], (int, float))
    ):
        return None
    return int(value[0]) + _global_offset(pattern), float(value[1])


def _global_offset(pattern: PatternResult) -> int:
    offset = pattern.metadata.get("window_start_index", 0)
    return int(offset) if isinstance(offset, (int, float)) else 0


def _global_index(pattern: PatternResult, name: str, default: int) -> int:
    value = pattern.metadata.get(name)
    return int(value) + _global_offset(pattern) if isinstance(value, int) else default


def _line_value(left: tuple[int, float], right: tuple[int, float], index: int) -> float:
    if right[0] == left[0]:
        return right[1]
    slope = (right[1] - left[1]) / (right[0] - left[0])
    return left[1] + slope * (index - left[0])


def _feature(
    name: str, value: float | bool, confidence: float
) -> FeatureResult:
    return FeatureResult(name, float(value), float(confidence))
