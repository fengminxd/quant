"""Stable identifiers and condition sets for fixed priority combinations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.models import FeatureResult, PatternResult


@dataclass(frozen=True)
class PriorityCombinationFeatureSet:
    """One applicable fixed combination and its independently testable conditions."""

    combination_id: str
    name: str
    condition_names: tuple[str, ...]
    features: Mapping[str, FeatureResult]


_PATTERN_PROFILES = {
    "PATTERN_003": (
        "FIXED_COMBO_005",
        "Three-point support priority combination",
        (
            "first_anchor_double_bottom_support",
            "all_three_anchors_close_above_ema99",
            "third_anchor_breakout_retest_support",
        ),
    ),
    "PATTERN_004": (
        "FIXED_COMBO_001",
        "Double-bottom support above EMA99",
        ("second_anchor_close_above_ema99",),
    ),
    "PATTERN_005": (
        "FIXED_COMBO_006",
        "Three-point resistance priority combination",
        (
            "first_anchor_horizontal_resistance",
            "third_anchor_open_below_ema99",
        ),
    ),
    "PATTERN_006": (
        "FIXED_COMBO_002",
        "Horizontal resistance below EMA99",
        ("second_anchor_open_below_ema99",),
    ),
    "PATTERN_007": (
        "FIXED_COMBO_003",
        "Inverse head-and-shoulders priority combination",
        ("head_close_above_ema99", "head_double_bottom_support"),
    ),
    "PATTERN_008": (
        "FIXED_COMBO_004",
        "Head-and-shoulders top priority combination",
        ("head_open_below_ema99", "head_horizontal_resistance"),
    ),
}


def priority_profile(
    pattern: PatternResult,
    groups: Mapping[str, tuple[int, ...]],
) -> tuple[str, str, tuple[str, ...]] | None:
    """Select one fixed combination from pattern identity and triangle geometry."""

    if pattern.pattern_id != "PATTERN_002":
        return _PATTERN_PROFILES.get(pattern.pattern_id)
    upper = groups.get("upper_points", ())
    lower = groups.get("lower_points", ())
    if len(upper) == 2 and len(lower) == 3:
        return (
            "FIXED_COMBO_007",
            "Bullish two-upper three-lower triangle combination",
            (
                "lower_first_anchor_double_bottom_support",
                "lower_third_anchor_close_above_ema99",
            ),
        )
    if len(upper) == 3 and len(lower) == 2:
        return (
            "FIXED_COMBO_008",
            "Bearish three-upper two-lower triangle combination",
            (
                "upper_first_anchor_horizontal_resistance",
                "upper_third_anchor_open_below_ema99",
            ),
        )
    return None
