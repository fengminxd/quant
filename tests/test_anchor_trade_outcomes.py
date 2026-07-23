from __future__ import annotations

import math
from pathlib import Path

import pytest

from backtest.anchor_outcomes import (
    AnchorTradeOutcome,
    AnchorTradeOutcomeEvaluator,
    AnchorTradePlan,
    summarize_outcomes,
)
from core.models import Bar
from features.trade_plan import TradeDirection
from research.anchor_trade_report import write_anchor_trade_report
from research.pattern_events import PatternAnchor, PatternScanEvent


def flat_bars(length: int = 10) -> list[Bar]:
    return [
        Bar(
            index * 3_600_000,
            100.0,
            100.5,
            99.5,
            100.0,
            1000.0,
            "1h",
        )
        for index in range(length)
    ]


def event(
    pattern_id: str,
    anchors: tuple[PatternAnchor, ...],
    bars: list[Bar],
    *,
    fixed: bool = False,
) -> PatternScanEvent:
    return PatternScanEvent(
        "BTC",
        "1h",
        pattern_id,
        pattern_id,
        "test_rule",
        80.0,
        bars[-1].timestamp,
        anchors,
        (anchors,),
        priority_fixed_combination=fixed,
        priority_combination_id="FIXED_COMBO_TEST" if fixed else None,
    )


@pytest.mark.parametrize(
    ("pattern_id", "count", "expected_position", "direction"),
    [
        ("PATTERN_004", 2, 1, "bullish"),
        ("PATTERN_006", 2, 1, "bearish"),
        ("PATTERN_007", 3, 2, "bullish"),
        ("PATTERN_008", 3, 2, "bearish"),
        ("PATTERN_003", 3, 2, "bullish"),
        ("PATTERN_005", 3, 2, "bearish"),
    ],
)
def test_non_triangle_entry_rules_select_requested_anchor(
    pattern_id: str,
    count: int,
    expected_position: int,
    direction: str,
) -> None:
    bars = flat_bars()
    anchors = tuple(
        PatternAnchor(index + 1, bars[index + 1].timestamp, 99.0 + index)
        for index in range(count)
    )

    plan = AnchorTradeOutcomeEvaluator().plan(
        event(pattern_id, anchors, bars),
        bars,
    )

    assert plan is not None
    assert plan.entry_anchor == anchors[expected_position]
    assert plan.direction == direction
    assert plan.stop_price == pytest.approx(
        plan.entry_price * (0.985 if direction == "bullish" else 1.015)
    )
    assert plan.target_price == pytest.approx(
        plan.entry_price * (1.015 if direction == "bullish" else 0.985)
    )
    assert plan.causal_at_anchor is False


def trend_bars(direction: int) -> list[Bar]:
    result = []
    for index in range(160):
        center = 100.0 + direction * 0.1 * index + 2.0 * math.sin(
            index * math.pi / 5.0
        )
        result.append(
            Bar(
                index * 3_600_000,
                center,
                center + 0.3,
                center - 0.3,
                center + direction * 0.05,
                1000.0,
                "1h",
            )
        )
    return result


@pytest.mark.parametrize(
    ("direction", "upper_indexes", "lower_indexes", "expected", "trade_direction"),
    [
        (1, (115, 135), (110, 125, 140), 140, "bullish"),
        (-1, (115, 130, 145), (110, 140), 145, "bearish"),
    ],
)
def test_triangle_entry_uses_frozen_prior_trend_and_third_boundary_anchor(
    direction: int,
    upper_indexes: tuple[int, ...],
    lower_indexes: tuple[int, ...],
    expected: int,
    trade_direction: str,
) -> None:
    bars = trend_bars(direction)
    upper = tuple(
        PatternAnchor(index, bars[index].timestamp, bars[index].high)
        for index in upper_indexes
    )
    lower = tuple(
        PatternAnchor(index, bars[index].timestamp, bars[index].low)
        for index in lower_indexes
    )
    scan_event = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_002",
        "Triangle",
        "triangle",
        80.0,
        bars[150].timestamp,
        tuple(sorted((*upper, *lower), key=lambda anchor: anchor.index)),
        (upper, lower),
    )

    plan = AnchorTradeOutcomeEvaluator().plan(scan_event, bars)

    assert plan is not None
    assert plan.entry_anchor.index == expected
    assert plan.direction == trade_direction
    assert plan.trend_score is not None


def plan_and_bars(direction: TradeDirection) -> tuple[AnchorTradePlan, list[Bar]]:
    bars = flat_bars(3)
    anchor = PatternAnchor(0, bars[0].timestamp, 100.0)
    scan_event = event("PATTERN_004", (anchor, anchor), bars)
    plan = AnchorTradePlan(
        scan_event,
        direction,
        anchor,
        100.0,
        98.5 if direction == "bullish" else 101.5,
        101.5 if direction == "bullish" else 98.5,
        "test",
        0,
    )
    return plan, bars


def test_same_bar_dual_touch_is_conservatively_counted_as_stop() -> None:
    plan, bars = plan_and_bars("bullish")
    bars[1] = Bar(bars[1].timestamp, 100.0, 102.0, 98.0, 100.0, 1000.0, "1h")

    outcome = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, bars)

    assert outcome.status == "stop_loss"
    assert outcome.simultaneous_touch is True
    assert outcome.net_return == pytest.approx(-0.0164)


def test_bearish_target_and_unresolved_are_distinguished() -> None:
    plan, bars = plan_and_bars("bearish")
    bars[1] = Bar(bars[1].timestamp, 100.0, 100.5, 98.0, 99.0, 1000.0, "1h")

    target = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, bars)
    pending = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, flat_bars(3))

    assert target.status == "take_profit"
    assert target.net_return == pytest.approx(0.0136)
    assert pending.status == "unresolved"


def test_summary_and_text_report_keep_fixed_combo_as_separate_cohort(
    tmp_path: Path,
) -> None:
    bars = flat_bars(4)
    bars[2] = Bar(bars[2].timestamp, 100.0, 102.0, 99.5, 101.0, 1000.0, "1h")
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    scan_event = event("PATTERN_004", anchors, bars, fixed=True)
    output = tmp_path / "outcomes.txt"

    write_anchor_trade_report(
        [scan_event],
        {"1h": bars},
        output,
        source_pdf="BTC.pdf",
    )
    text = output.read_text(encoding="utf-8")
    outcome = AnchorTradeOutcomeEvaluator().evaluate(scan_event, bars)
    assert outcome is not None
    summary = summarize_outcomes([outcome])

    assert summary.take_profit == 1
    assert "全部符合入场规则案例" in text
    assert "FIXED_COMBO 符合入场规则案例" in text
    assert "止盈: 1 (100.00% / 全部案例)" in text
    assert "不重新" not in text
