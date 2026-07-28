"""Plain-text reporting for causal Pattern structure-retest outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from backtest.anchor_outcomes import (
    AnchorTradeOutcome,
    AnchorTradeOutcomeEvaluator,
    AnchorTradeSummary,
    summarize_outcomes,
)
from core.models import Bar
from core.pattern_policy import is_trade_event_enabled
from research.pattern_events import PatternScanEvent
from research.pattern_scan import format_utc_plus_8


def write_anchor_trade_report(
    events: Sequence[PatternScanEvent],
    bars_by_timeframe: Mapping[str, Sequence[Bar]],
    output_path: str | Path,
    *,
    source_pdf: str | Path,
    evaluator: AnchorTradeOutcomeEvaluator | None = None,
) -> Path:
    """Evaluate configurable barriers and write a UTF-8 report without redrawing."""

    events = tuple(
        event
        for event in events
        if is_trade_event_enabled(
            event.pattern_id,
            event.priority_combination_id,
        )
    )
    engine = evaluator or AnchorTradeOutcomeEvaluator()
    outcomes: list[AnchorTradeOutcome] = []
    excluded: list[PatternScanEvent] = []
    for event in events:
        outcome = engine.evaluate(event, bars_by_timeframe[event.timeframe])
        if outcome is None:
            excluded.append(event)
        else:
            outcomes.append(outcome)
    fixed = [
        outcome
        for outcome in outcomes
        if outcome.plan.event.priority_fixed_combination
    ]
    fixed_excluded = [
        event for event in excluded if event.priority_fixed_combination
    ]
    lines = _report_header(
        source_pdf,
        events,
        outcomes,
        excluded,
        engine,
    )
    lines.extend(_summary_lines("全部符合入场规则案例", summarize_outcomes(outcomes)))
    lines.extend(
        _summary_lines("FIXED_COMBO 符合入场规则案例", summarize_outcomes(fixed))
    )
    lines.extend(
        (
            f"FIXED_COMBO 未满足趋势/结构回踩条件: {len(fixed_excluded)}",
            "",
        )
    )
    for status, title in (
        ("stop_loss", "止损案例"),
        ("protected_profit", "触发 1.5% 保护止盈案例"),
        ("take_profit", "达到 3% 最终止盈案例"),
        ("unresolved", "截至数据末尾未触发案例"),
    ):
        selected = [outcome for outcome in outcomes if outcome.status == status]
        lines.extend((f"=== {title} ({len(selected)}) ===",))
        lines.extend(_outcome_line(outcome) for outcome in selected)
        lines.append("")
    lines.append(f"=== 不满足入场规则的扫描案例 ({len(excluded)}) ===")
    lines.extend(_excluded_line(event) for event in excluded)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return target


def _report_header(
    source_pdf: str | Path,
    events: Sequence[PatternScanEvent],
    outcomes: Sequence[AnchorTradeOutcome],
    excluded: Sequence[PatternScanEvent],
    evaluator: AnchorTradeOutcomeEvaluator,
) -> list[str]:
    costs = evaluator.costs
    causal_count = sum(outcome.plan.causal_at_entry for outcome in outcomes)
    simultaneous = sum(outcome.simultaneous_touch for outcome in outcomes)
    entry = evaluator.entry_resolver.entry_extractor
    cohort = (
        f"{events[0].symbol} {events[0].timeframe}"
        if events
        else "Empty"
    )
    return [
        f"{cohort} Pattern 锚点交易结果统计",
        f"规则明细同步输出: {source_pdf}",
        f"去重形态数: {len(events)}",
        f"符合指定入场规则: {len(outcomes)}",
        f"不满足趋势/结构锚点/回踩条件: {len(excluded)}",
        "",
        "统计口径:",
        (
            "- PATTERN_006 不作为独立入场规则；仅 FIXED_COMBO_002 中的 "
            "PATTERN_006 可入场，其阻力逻辑仍供 FIXED_COMBO_004/008 使用；"
            "PATTERN_008 禁止交易和报告；FIXED_COMBO_006 全局禁用。"
        ),
        (
            "- Pattern 确认后等待结构区回踩；K 线触及结构区并按方向重新"
            "收回时，以该 K 线收盘价入场。"
        ),
        (
            f"- 结构区宽度 {entry.zone_width_atr:.2f} ATR，收盘距结构位不超过 "
            f"{entry.max_close_distance_atr:.2f} ATR，最多等待 "
            f"{entry.max_wait_bars} 根 K 线。"
        ),
        "- 从入场 K 线后的下一根 K 线开始检查，不使用入场柱内未知路径。",
        (
            f"- 止损比例 {evaluator.stop_loss_ratio:.4%}，"
            f"浮盈达到 {evaluator.lock_trigger_ratio:.4%} 后，将保护止损移至"
            f"盈利 {evaluator.lock_trigger_ratio:.4%} 的价格，"
            f"最终止盈 {evaluator.take_profit_ratio:.4%}，"
            f"Gross R:R "
            f"{evaluator.take_profit_ratio / evaluator.stop_loss_ratio:.2f}；"
            "空单方向相反。"
        ),
        (
            "- 保护止损从触发浮盈阈值后的下一根 K 线生效；触发柱若同时"
            "触及原止损，仍按原止损处理。"
        ),
        (
            "- 保护生效后，同一根 K 线同时触及保护止损和最终止盈时，"
            "按保守原则计为保护止盈。"
        ),
        "- 未决案例计入总案例分母；同时另列仅已平仓案例占比。",
        (
            "- 倒头肩/头肩顶等待右肩区域回踩并重新收回；三角趋势冻结在"
            "最早边界锚点，上涨用下边界 P3、下跌用上边界 P3。"
        ),
        (
            "- 成本估计: 开单手续费 "
            f"{costs.entry_fee_rate:.4%}，平仓手续费 "
            f"{costs.exit_fee_rate:.4%}，单边滑点 "
            f"{costs.slippage_rate_per_side:.4%}，资金费 "
            f"{costs.funding_rate:.4%}。"
        ),
        f"- 入场时已因果确认 Pattern 的案例: {causal_count}/{len(outcomes)}",
        f"- 同根 K 线双触发并按止损处理: {simultaneous}",
        "",
    ]


def _summary_lines(title: str, summary: AnchorTradeSummary) -> list[str]:
    return [
        f"=== {title} ===",
        f"总案例: {summary.total}",
        (
            f"3% 最终止盈: {summary.take_profit} "
            f"({summary.percentage(summary.take_profit):.2f}% / 全部案例)"
        ),
        (
            f"1.5% 保护止盈: {summary.protected_profit} "
            f"({summary.percentage(summary.protected_profit):.2f}% / 全部案例)"
        ),
        (
            f"止损: {summary.stop_loss} "
            f"({summary.percentage(summary.stop_loss):.2f}% / 全部案例)"
        ),
        (
            f"未决: {summary.unresolved} "
            f"({summary.percentage(summary.unresolved):.2f}% / 全部案例)"
        ),
        (
            f"仅已平仓占比: 盈利平仓 "
            f"{summary.resolved_percentage(summary.profitable):.2f}%，止损 "
            f"{summary.resolved_percentage(summary.stop_loss):.2f}%"
        ),
        "",
    ]


def _outcome_line(outcome: AnchorTradeOutcome) -> str:
    plan = outcome.plan
    event = plan.event
    combo = event.priority_combination_id or "-"
    conditions = (
        ",".join(event.priority_matched_conditions)
        if event.priority_fixed_combination
        else "-"
    )
    exit_time = (
        format_utc_plus_8(outcome.exit_timestamp)
        if outcome.exit_timestamp is not None
        else "-"
    )
    net = f"{outcome.net_return:.4%}" if outcome.net_return is not None else "-"
    lock_time = (
        format_utc_plus_8(outcome.lock_timestamp)
        if outcome.lock_timestamp is not None
        else "-"
    )
    exit_price = (
        f"{outcome.exit_price:.8f}" if outcome.exit_price is not None else "-"
    )
    lock_trigger = plan.lock_trigger_price or plan.entry_price
    locked_stop = plan.locked_stop_price or lock_trigger
    structure = plan.structure_anchor or plan.entry_anchor
    return (
        f"symbol={event.symbol} timeframe={event.timeframe} "
        f"pattern={event.pattern_id} rule={event.rule} outcome={outcome.status} "
        f"combo={combo} "
        f"conditions=[{conditions}] direction={plan.direction} "
        f"entry_rule={plan.entry_rule!r} "
        f"structure_time={format_utc_plus_8(structure.timestamp)} "
        f"structure_level={structure.price:.8f} "
        f"entry_time={format_utc_plus_8(plan.entry_anchor.timestamp)} "
        f"entry={plan.entry_price:.8f} stop={plan.stop_price:.8f} "
        f"target={plan.target_price:.8f} "
        f"lock_trigger={lock_trigger:.8f} locked_stop={locked_stop:.8f} "
        f"lock_time={lock_time} exit_time={exit_time} exit={exit_price} "
        f"bars_held={outcome.bars_held if outcome.bars_held is not None else '-'} "
        f"net_return_after_cost={net} simultaneous={outcome.simultaneous_touch} "
        f"detected_time={format_utc_plus_8(event.detected_timestamp)} "
        f"confirmation_delay_bars={plan.confirmation_delay_bars} "
        f"entry_wait_bars={plan.entry_wait_bars} "
        f"entry_quality={plan.entry_quality_score if plan.entry_quality_score is not None else '-'} "
        f"causal_at_entry={plan.causal_at_entry}"
    )


def _excluded_line(event: PatternScanEvent) -> str:
    anchors = ",".join(
        format_utc_plus_8(anchor.timestamp) for anchor in event.anchors
    )
    return (
        f"symbol={event.symbol} timeframe={event.timeframe} "
        f"pattern={event.pattern_id} rule={event.rule} "
        f"combo={event.priority_combination_id or '-'} "
        f"detected_time={format_utc_plus_8(event.detected_timestamp)} "
        f"anchors=[{anchors}] "
        "reason=no eligible trend/anchor or no retest-and-reclaim before expiry"
    )
