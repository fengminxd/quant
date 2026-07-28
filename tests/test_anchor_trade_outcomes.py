from __future__ import annotations

from pathlib import Path

import pytest

from backtest.anchor_outcomes import (
    AnchorTradeOutcome,
    AnchorTradeOutcomeEvaluator,
    AnchorTradePlan,
    summarize_outcomes,
)
from core.models import Bar
from features.trade_feasibility import TransactionCostModel
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
    detected_index: int | None = None,
) -> PatternScanEvent:
    detected = len(bars) - 1 if detected_index is None else detected_index
    combination_id = (
        "FIXED_COMBO_002"
        if pattern_id == "PATTERN_006"
        else ("FIXED_COMBO_TEST" if fixed else None)
    )
    return PatternScanEvent(
        "BTC",
        "1h",
        pattern_id,
        pattern_id,
        "test_rule",
        80.0,
        bars[detected].timestamp,
        anchors,
        (anchors,),
        priority_fixed_combination=combination_id is not None,
        priority_combination_id=combination_id,
    )


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
        103.0 if direction == "bullish" else 97.0,
        "test",
        0,
        lock_trigger_price=101.5 if direction == "bullish" else 98.5,
        locked_stop_price=101.5 if direction == "bullish" else 98.5,
    )
    return plan, bars


def test_same_bar_dual_touch_is_conservatively_counted_as_stop() -> None:
    plan, bars = plan_and_bars("bullish")
    bars[1] = Bar(bars[1].timestamp, 100.0, 104.0, 98.0, 100.0, 1000.0, "1h")

    outcome = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, bars)

    assert outcome.status == "stop_loss"
    assert outcome.simultaneous_touch is True
    assert outcome.net_return == pytest.approx(-0.0161)


def test_bearish_final_target_and_unresolved_are_distinguished() -> None:
    plan, bars = plan_and_bars("bearish")
    bars[1] = Bar(bars[1].timestamp, 100.0, 100.5, 96.5, 97.0, 1000.0, "1h")

    target = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, bars)
    pending = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, flat_bars(3))

    assert target.status == "take_profit"
    assert target.net_return == pytest.approx(0.0289)
    assert pending.status == "unresolved"


def test_profit_lock_activates_on_the_candle_after_trigger() -> None:
    plan, bars = plan_and_bars("bullish")
    bars[1] = Bar(
        bars[1].timestamp, 100.0, 102.0, 100.0, 101.8, 1000.0, "1h"
    )
    bars[2] = Bar(
        bars[2].timestamp, 101.8, 102.0, 101.0, 101.4, 1000.0, "1h"
    )

    outcome = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, bars)

    assert outcome.status == "protected_profit"
    assert outcome.exit_price == pytest.approx(101.5)
    assert outcome.lock_timestamp == bars[1].timestamp
    assert outcome.bars_held == 2
    assert outcome.net_return == pytest.approx(0.0139)


def test_locked_stop_wins_same_bar_ambiguity_against_final_target() -> None:
    plan, bars = plan_and_bars("bullish")
    bars[1] = Bar(
        bars[1].timestamp, 100.0, 102.0, 100.0, 101.8, 1000.0, "1h"
    )
    bars[2] = Bar(
        bars[2].timestamp, 101.8, 103.5, 101.0, 102.0, 1000.0, "1h"
    )

    outcome = AnchorTradeOutcomeEvaluator().evaluate_plan(plan, bars)

    assert outcome.status == "protected_profit"
    assert outcome.simultaneous_touch is True


def test_summary_and_text_report_keep_fixed_combo_as_separate_cohort(
    tmp_path: Path,
) -> None:
    bars = flat_bars(4)
    bars[2] = Bar(
        bars[2].timestamp, 100.0, 100.4, 99.6, 100.05, 1000.0, "1h"
    )
    bars[3] = Bar(
        bars[3].timestamp, 100.05, 103.5, 100.0, 103.1, 1000.0, "1h"
    )
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    scan_event = event(
        "PATTERN_004", anchors, bars, fixed=True, detected_index=1
    )
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
    assert summary.protected_profit == 0
    assert "全部符合入场规则案例" in text
    assert "FIXED_COMBO 符合入场规则案例" in text
    assert "3% 最终止盈: 1 (100.00% / 全部案例)" in text
    assert "不重新" not in text


@pytest.mark.parametrize(
    ("pattern_id", "direction", "expected_stop", "expected_target"),
    [
        ("PATTERN_004", "bullish", 99.0, 103.0),
        ("PATTERN_006", "bearish", 101.0, 97.0),
    ],
)
def test_asymmetric_stop_and_target_ratios(
    pattern_id: str,
    direction: str,
    expected_stop: float,
    expected_target: float,
) -> None:
    bars = flat_bars()
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    evaluator = AnchorTradeOutcomeEvaluator(
        stop_loss_ratio=0.01,
        take_profit_ratio=0.03,
    )

    plan = evaluator.plan(
        event(pattern_id, anchors, bars, detected_index=8), bars
    )

    assert plan is not None
    assert plan.direction == direction
    assert plan.stop_price == pytest.approx(expected_stop)
    assert plan.lock_trigger_price == pytest.approx(
        101.5 if direction == "bullish" else 98.5
    )
    assert plan.target_price == pytest.approx(expected_target)


def test_report_displays_configured_barriers_and_reward_risk(tmp_path: Path) -> None:
    bars = flat_bars(4)
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    output = tmp_path / "configured.txt"

    write_anchor_trade_report(
        [event("PATTERN_004", anchors, bars, detected_index=1)],
        {"1h": bars},
        output,
        source_pdf="rules.pdf",
        evaluator=AnchorTradeOutcomeEvaluator(
            stop_loss_ratio=0.01,
            take_profit_ratio=0.03,
        ),
    )

    text = output.read_text(encoding="utf-8")
    assert "止损比例 1.0000%" in text
    assert "最多等待 11 根 K 线" in text
    assert "浮盈达到 1.5000%" in text
    assert "最终止盈 3.0000%" in text
    assert "Gross R:R 3.00" in text
    assert "stop=99.00000000 target=103.00000000" in text
    assert "lock_trigger=101.50000000 locked_stop=101.50000000" in text


def test_report_uses_configured_entry_and_exit_fees(tmp_path: Path) -> None:
    bars = flat_bars(4)
    bars[2] = Bar(
        bars[2].timestamp, 100.0, 100.4, 99.6, 100.0, 1000.0, "1h"
    )
    bars[3] = Bar(
        bars[3].timestamp, 100.0, 103.5, 99.5, 103.0, 1000.0, "1h"
    )
    anchors = (
        PatternAnchor(0, bars[0].timestamp, 100.0),
        PatternAnchor(1, bars[1].timestamp, 100.0),
    )
    output = tmp_path / "configured_costs.txt"

    write_anchor_trade_report(
        [event("PATTERN_004", anchors, bars, detected_index=1)],
        {"1h": bars},
        output,
        source_pdf="rules.pdf",
        evaluator=AnchorTradeOutcomeEvaluator(
            costs=TransactionCostModel(
                entry_fee_rate=0.0003,
                exit_fee_rate=0.0007,
                slippage_rate_per_side=0.0,
            ),
        ),
    )

    text = output.read_text(encoding="utf-8")
    assert "开单手续费 0.0300%" in text
    assert "平仓手续费 0.0700%" in text
    assert "net_return_after_cost=2.9000%" in text


def test_profit_lock_must_be_below_final_target() -> None:
    with pytest.raises(ValueError, match="below take_profit_ratio"):
        AnchorTradeOutcomeEvaluator(
            lock_trigger_ratio=0.03,
            take_profit_ratio=0.03,
        )
