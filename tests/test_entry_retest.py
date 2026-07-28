from __future__ import annotations

from collections.abc import Sequence

import pytest

from core.models import Bar, FeatureResult, PatternResult
from factors.trade_feasibility import PatternTradeFeasibilityScorer
from features.entry_retest import EntryRetestFeatureExtractor
from features.trade_feasibility import TransactionCostModel
from features.trade_plan import PatternTradePlanExtractor
from indicators.swing import Pivot


def bars() -> list[Bar]:
    return [
        Bar(index, 15.0, 15.5, 14.5, 15.0, 1000.0, "4h")
        for index in range(60)
    ]


def retest_bars(level: float, direction: str) -> list[Bar]:
    source = bars()
    close = level + 0.05 if direction == "bullish" else level - 0.05
    source[-1] = Bar(
        59, level, level + 0.40, level - 0.40, close, 1000.0, "4h"
    )
    return source


class StaticSwingDetector:
    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        return [Pivot(20, 21, 20.0, "high"), Pivot(30, 31, 10.0, "low")]


class StaticContextExtractor:
    def __init__(self, direction: str) -> None:
        self.direction = direction

    def extract(self, data: Sequence[Bar]) -> dict[str, FeatureResult]:
        bullish = self.direction == "bullish"
        return {
            "higher_high_ratio": FeatureResult(
                "higher_high_ratio", 1.0 if bullish else 0.0, 1.0
            ),
            "higher_low_ratio": FeatureResult(
                "higher_low_ratio", 1.0 if bullish else 0.0, 1.0
            ),
            "lower_high_ratio": FeatureResult(
                "lower_high_ratio", 0.0 if bullish else 1.0, 1.0
            ),
            "lower_low_ratio": FeatureResult(
                "lower_low_ratio", 0.0 if bullish else 1.0, 1.0
            ),
            "trend_efficiency_signed": FeatureResult(
                "trend_efficiency_signed", 0.5 if bullish else -0.5, 1.0
            ),
            "trend_comparison_count": FeatureResult(
                "trend_comparison_count", 4.0, 1.0
            ),
        }


@pytest.mark.parametrize(
    ("pattern_id", "geometry", "direction", "stop_side", "level", "enabled"),
    [
        (
            "PATTERN_003",
            {"line": {"start": (0, 10.0), "end": (40, 11.0)}},
            "bullish", "below", 11.475, True,
        ),
        ("PATTERN_004", {"level": 11.0}, "bullish", "below", 11.0, True),
        ("PATTERN_006", {"level": 19.0}, "bearish", "above", 19.0, False),
    ],
)
def test_line_and_horizontal_rules_require_retest_and_reclaim(
    pattern_id: str,
    geometry: dict[str, object],
    direction: str,
    stop_side: str,
    level: float,
    enabled: bool,
) -> None:
    pattern = PatternResult(
        pattern_id,
        pattern_id,
        True,
        80.0,
        geometry=geometry,
        metadata={"detected_at_index": 58},
    )
    extractor = PatternTradePlanExtractor(swing_detector=StaticSwingDetector())

    plan, _, _ = extractor.extract(pattern, retest_bars(level, direction))

    if not enabled:
        assert plan is None
        return
    assert plan is not None
    assert plan.direction == direction
    assert plan.target_source == "confirmed_swing_liquidity"
    assert plan.target_price == (20.0 if direction == "bullish" else 10.0)
    assert (plan.stop_price < plan.entry_price) == (stop_side == "below")


def triangle_pattern(breakout: str | None) -> PatternResult:
    return PatternResult(
        "PATTERN_002",
        "Triangle",
        True,
        70.0,
        geometry={
            "upper_points": [(5, 120.0), (25, 115.0), (45, 110.0)],
            "lower_points": [(10, 80.0), (30, 85.0), (50, 90.0)],
            "upper_line": {"start": (5, 120.0), "end": (45, 110.0)},
            "lower_line": {"start": (10, 80.0), "end": (50, 90.0)},
        },
        metadata={
            "breakout_direction": breakout,
            "state": "structure_confirmed",
            "detected_at_index": 58,
        },
    )


@pytest.mark.parametrize(
    ("direction", "entry_level", "entry_source"),
    [
        ("bullish", 90.0, "triangle_lower_third_anchor"),
        ("bearish", 110.0, "triangle_upper_third_anchor"),
    ],
)
def test_triangle_uses_prior_trend_and_directional_third_anchor(
    direction: str,
    entry_level: float,
    entry_source: str,
) -> None:
    entry_extractor = EntryRetestFeatureExtractor(
        context_extractor=StaticContextExtractor(direction)
    )
    scorer = PatternTradeFeasibilityScorer(
        extractor=PatternTradePlanExtractor(entry_extractor=entry_extractor),
        costs=TransactionCostModel(
            entry_fee_rate=0.0,
            exit_fee_rate=0.0,
            slippage_rate_per_side=0.0,
        ),
    )

    evaluation = scorer.score(
        triangle_pattern("downside" if direction == "bullish" else "upside"),
        retest_bars(entry_level, direction),
    )

    assert evaluation.plan is not None
    assert evaluation.plan.direction == direction
    assert evaluation.plan.entry_source == entry_source
    assert evaluation.plan.structure_level == entry_level
    assert evaluation.plan.target_source == "triangle_opposite_boundary"
    assert evaluation.entry_quality is not None
    assert evaluation.entry_quality.metadata["active"] is True


def test_triangle_without_established_prior_trend_cannot_enter() -> None:
    evaluation = PatternTradeFeasibilityScorer().score(
        triangle_pattern("downside"), retest_bars(110.0, "bearish")
    )

    assert evaluation.plan is None
    assert evaluation.entry_quality is not None
    assert evaluation.entry_quality.metadata["active"] is False


@pytest.mark.parametrize(
    ("pattern_id", "points", "neckline", "direction", "right_shoulder"),
    [
        (
            "PATTERN_007",
            [(5, 10.0), (20, 8.0), (40, 10.0)],
            [(12, 12.0), (30, 12.0)],
            "bullish",
            10.0,
        ),
    ],
)
def test_head_shoulders_use_right_shoulder_reclaim(
    pattern_id: str,
    points: list[tuple[int, float]],
    neckline: list[tuple[int, float]],
    direction: str,
    right_shoulder: float,
) -> None:
    pattern = PatternResult(
        pattern_id,
        pattern_id,
        True,
        80.0,
        geometry={"points": points, "neckline_points": neckline},
        metadata={"state": "structure_confirmed", "detected_at_index": 58},
    )

    plan, _, _ = PatternTradePlanExtractor().extract(
        pattern, retest_bars(right_shoulder, direction)
    )

    assert plan is not None
    expected = plan.entry_price + 4.0 if direction == "bullish" else plan.entry_price - 4.0
    assert plan.target_price == pytest.approx(expected)
    assert plan.target_source == "head_neckline_measured_move"
    assert plan.entry_source == "right_shoulder_zone"
    assert plan.structure_level == right_shoulder


@pytest.mark.parametrize(
    ("pattern_id", "points", "neckline"),
    [
        (
            "PATTERN_007",
            [(5, 10.0), (20, 8.0), (40, 10.0)],
            [(12, 12.0), (30, 12.0)],
        ),
    ],
)
def test_head_shoulders_waits_without_right_shoulder_retest(
    pattern_id: str,
    points: list[tuple[int, float]],
    neckline: list[tuple[int, float]],
) -> None:
    pattern = PatternResult(
        pattern_id,
        pattern_id,
        True,
        80.0,
        geometry={"points": points, "neckline_points": neckline},
        metadata={"state": "structure_confirmed", "detected_at_index": 58},
    )

    plan, _, _ = PatternTradePlanExtractor().extract(pattern, bars())

    assert plan is None
