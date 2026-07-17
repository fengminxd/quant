from __future__ import annotations

from collections.abc import Callable

import pytest

from core.models import Bar, PatternResult
from factors.pattern_context import PatternContextScorer
from factors.trade_feasibility import PatternTradeFeasibilityScorer
from features.trade_feasibility import TransactionCostModel
from features.trade_plan import PatternTradePlan
from indicators.swing import PivotDetector, SwingDetector
from patterns import HorizontalSupport, ThreePointTrendlineSupport
from tests.test_head_shoulders_top import detector as top_detector
from tests.test_head_shoulders_top import top_bars
from tests.test_horizontal_resistance import detector as horizontal_resistance_detector
from tests.test_horizontal_resistance import resistance_bars as horizontal_resistance_bars
from tests.test_inverse_head_shoulders import detector as bottom_detector
from tests.test_inverse_head_shoulders import pattern_bars as bottom_bars
from tests.test_patterns import horizontal_double_low_bars, strict_three_point_bars
from tests.test_three_point_trendline_resistance import detector as trendline_resistance_detector
from tests.test_three_point_trendline_resistance import resistance_bars as trendline_resistance_bars


def three_point_support_case() -> tuple[list[Bar], PatternResult]:
    bars = strict_three_point_bars()
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    result = ThreePointTrendlineSupport(swing, atr_tolerance_ratio=0.1).detect(bars)
    return bars, result


def horizontal_support_case() -> tuple[list[Bar], PatternResult]:
    bars = horizontal_double_low_bars()
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    result = HorizontalSupport(swing, atr_tolerance_ratio=0.1).detect(bars)
    return bars, result


def three_point_resistance_case() -> tuple[list[Bar], PatternResult]:
    bars = trendline_resistance_bars()
    return bars, trendline_resistance_detector().detect(bars)


def horizontal_resistance_case() -> tuple[list[Bar], PatternResult]:
    bars = horizontal_resistance_bars()
    return bars, horizontal_resistance_detector().detect(bars)


def inverse_head_shoulders_case() -> tuple[list[Bar], PatternResult]:
    bars = bottom_bars()
    return bars, bottom_detector().detect(bars)


def head_shoulders_top_case() -> tuple[list[Bar], PatternResult]:
    bars = top_bars()
    return bars, top_detector().detect(bars)


@pytest.mark.parametrize(
    "case",
    [
        three_point_support_case,
        horizontal_support_case,
        three_point_resistance_case,
        horizontal_resistance_case,
        inverse_head_shoulders_case,
        head_shoulders_top_case,
    ],
)
def test_existing_pattern_results_feed_context_profiles(
    case: Callable[[], tuple[list[Bar], PatternResult]],
) -> None:
    bars, pattern = case()

    evaluation = PatternContextScorer().score(pattern, bars)

    assert pattern.detected is True
    assert evaluation.composite.metadata["gate_passed"] is True
    assert evaluation.composite.metadata["pattern_id"] == pattern.pattern_id
    assert evaluation.composite.metadata["selected_factors"]
    assert 0.0 <= evaluation.composite.score <= 100.0


@pytest.mark.parametrize(
    "case",
    [
        three_point_support_case,
        horizontal_support_case,
        three_point_resistance_case,
        horizontal_resistance_case,
        inverse_head_shoulders_case,
        head_shoulders_top_case,
    ],
)
def test_existing_pattern_results_feed_trade_feasibility(
    case: Callable[[], tuple[list[Bar], PatternResult]],
) -> None:
    bars, pattern = case()
    bullish = pattern.pattern_id in {"PATTERN_003", "PATTERN_004", "PATTERN_007"}
    entry = bars[-1].close
    plan = PatternTradePlan(
        "bullish" if bullish else "bearish",
        entry,
        entry - 1.0 if bullish else entry + 1.0,
        entry + 3.0 if bullish else entry - 3.0,
    )
    scorer = PatternTradeFeasibilityScorer(
        costs=TransactionCostModel(0.0, 0.0, 0.0)
    )

    evaluation = scorer.score(pattern, bars, plan=plan)

    assert evaluation.factor.metadata["pattern_gate_passed"] is True
    assert evaluation.factor.metadata["active"] is True
    assert evaluation.factor.metadata["feasible"] is True
    assert evaluation.factor.metadata["emits_signal"] is False
    assert evaluation.factor.score == 100.0
