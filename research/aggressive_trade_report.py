"""Standalone reporting for confirmed-pivot reference limit entries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from backtest.aggressive_anchor_strategy import (
    AggressiveAnchorStrategyEvaluator,
    AggressiveTradeOutcome,
    AggressiveTradeSummary,
    summarize_aggressive_outcomes,
)
from core.models import Bar
from core.pattern_policy import is_trade_event_enabled
from research.pattern_events import PatternScanEvent
from research.pattern_scan import format_utc_plus_8


def write_aggressive_trade_report(
    events: Sequence[PatternScanEvent],
    bars_by_timeframe: Mapping[str, Sequence[Bar]],
    output_path: str | Path,
    *,
    start: datetime,
    end: datetime,
    evaluator: AggressiveAnchorStrategyEvaluator | None = None,
) -> Path:
    """Scan-event outcomes into a report without reading prior reports or PDFs."""

    events = tuple(
        event
        for event in events
        if is_trade_event_enabled(
            event.pattern_id,
            event.priority_combination_id,
        )
    )
    engine = evaluator or AggressiveAnchorStrategyEvaluator()
    outcomes: list[AggressiveTradeOutcome] = []
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
    lines = _header(start, end, events, outcomes, excluded, engine)
    lines.extend(
        _summary_lines(
            "全部符合激进入场规则案例",
            summarize_aggressive_outcomes(outcomes),
            engine,
        )
    )
    lines.extend(
        _summary_lines(
            "FIXED_COMBO 符合激进入场规则案例",
            summarize_aggressive_outcomes(fixed),
            engine,
        )
    )
    lines.extend(
        (
            f"FIXED_COMBO 挂单失效或参考K线不合格: {len(fixed_excluded)}",
            "",
        )
    )
    sections = (
        ("stop_loss", "止损案例"),
        (
            "protected_profit",
            f"触发{_percentage_label(engine.lock_trigger_ratio)}保护止损案例",
        ),
        ("take_profit", f"达到{_percentage_label(engine.take_profit_ratio)}止盈案例"),
        ("unresolved", "截至数据末尾未触发案例"),
    )
    for status, title in sections:
        selected = [outcome for outcome in outcomes if outcome.status == status]
        lines.append(f"=== {title} ({len(selected)}) ===")
        lines.extend(_outcome_line(outcome) for outcome in selected)
        lines.append("")
    lines.append(f"=== 激进参考挂单未成交或不合格结构 ({len(excluded)}) ===")
    lines.extend(_excluded_line(event) for event in excluded)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return target


def _header(
    start: datetime,
    end: datetime,
    events: Sequence[PatternScanEvent],
    outcomes: Sequence[AggressiveTradeOutcome],
    excluded: Sequence[PatternScanEvent],
    evaluator: AggressiveAnchorStrategyEvaluator,
) -> list[str]:
    costs = evaluator.costs
    causal = sum(outcome.plan.causal_at_entry for outcome in outcomes)
    simultaneous = sum(outcome.simultaneous_touch for outcome in outcomes)
    cohort = (
        f"{events[0].symbol} {events[0].timeframe}"
        if events
        else "Empty"
    )
    return [
        f"{cohort} 激进开单策略结果统计",
        "数据来源: 数据库历史已收盘K线独立扫描；不读取任何既有PDF或开单报告。",
        f"扫描范围: {start:%Y-%m-%d %H:%M:%S} UTC+8 至 "
        f"{end:%Y-%m-%d %H:%M:%S} UTC+8",
        f"时间去重后结构数: {len(events)}",
        f"六根K线内成交: {len(outcomes)}",
        f"挂单失效或参考K线不合格: {len(excluded)}",
        "",
        "统计口径:",
        (
            "- PATTERN_006 不作为独立入场规则；仅 FIXED_COMBO_002 中的 "
            "PATTERN_006 可入场，其阻力逻辑仍供 FIXED_COMBO_004/008 使用；"
            "PATTERN_008 禁止交易和报告；FIXED_COMBO_006 全局禁用。"
        ),
        (
            "- 指定末端锚点必须完成右侧 Pivot Low / Pivot High 确认；"
            "确认K线收盘后才生成参考挂单。"
        ),
        (
            "- 买入：锚点下影线不长于实体时取最低价，下影线长于实体时"
            "阳线取开盘价、阴线取收盘价，十字星取最低价；卖出：锚点"
            "上影线不长于实体时取最高价，上影线长于实体时阳线取收盘价、"
            "阴线取开盘价，十字星取最高价。"
        ),
        (
            f"- 从锚点确认后的第1根至第{evaluator.max_entry_wait_bars}根K线"
            "检查成交；买单 low<=参考价，卖单 high>=参考价，超时失效。"
        ),
        "- 成交K线内不判断出场，止损/止盈从成交后的下一根K线开始检查。",
        (
            f"- 初始止损 {evaluator.stop_loss_ratio:.4%}；浮盈达到 "
            f"{evaluator.lock_trigger_ratio:.4%} 后，将保护止损设在浮盈 "
            f"{evaluator.lock_trigger_ratio:.4%} 价格；最终止盈 "
            f"{evaluator.take_profit_ratio:.4%}。"
        ),
        "- 保护止损从触发K线的下一根K线开始生效，避免假设触发K线内路径。",
        (
            "- 已激活保护后，同根K线同时触发保护止损与"
            f"{evaluator.take_profit_ratio:.4%}止盈时，保护止损优先。"
        ),
        "- 初始止损与盈利障碍同根触发时，按保守原则计为初始止损。",
        "- 未决案例计入总案例分母；同时另列仅已平仓案例占比。",
        (
            "- 三角方向由最早边界锚点处的既有趋势冻结：上涨取下边界P3"
            "买入，下跌取上边界P3卖出。"
        ),
        (
            f"- 成本估计: 开单手续费 {costs.entry_fee_rate:.4%}，"
            f"平仓手续费 {costs.exit_fee_rate:.4%}，单边滑点 "
            f"{costs.slippage_rate_per_side:.4%}，资金费 "
            f"{costs.funding_rate:.4%}。"
        ),
        "- 限价触碰基于OHLC；未模拟盘口排队、跳空改善或部分成交。",
        f"- 入场前末端 Pivot 已因果确认: {causal}/{len(outcomes)}",
        f"- 同根K线多障碍触发并按保守规则处理: {simultaneous}",
        "",
    ]


def _summary_lines(
    title: str,
    summary: AggressiveTradeSummary,
    evaluator: AggressiveAnchorStrategyEvaluator,
) -> list[str]:
    take_profit = _percentage_label(evaluator.take_profit_ratio)
    protected_profit = _percentage_label(evaluator.lock_trigger_ratio)
    return [
        f"=== {title} ===",
        f"总案例: {summary.total}",
        (
            f"{take_profit}止盈: {summary.take_profit} "
            f"({summary.percentage(summary.take_profit):.2f}% / 全部案例)"
        ),
        (
            f"{protected_profit}保护止盈: {summary.protected_profit} "
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
            f"仅已平仓占比: 盈利 "
            f"{summary.resolved_percentage(summary.profitable):.2f}%，止损 "
            f"{summary.resolved_percentage(summary.stop_loss):.2f}%"
        ),
        "",
    ]


def _percentage_label(value: float) -> str:
    """Format a strategy ratio compactly for human-facing section labels."""

    return f"{value * 100:g}%"


def _outcome_line(outcome: AggressiveTradeOutcome) -> str:
    plan = outcome.plan
    event = plan.event
    conditions = (
        ",".join(event.priority_matched_conditions)
        if event.priority_fixed_combination
        else "-"
    )
    exit_time = _time(outcome.exit_timestamp)
    lock_time = _time(outcome.lock_timestamp)
    net = f"{outcome.net_return:.4%}" if outcome.net_return is not None else "-"
    anchor_spans = _anchor_span_fields(event)
    return (
        f"symbol={event.symbol} timeframe={event.timeframe} "
        f"pattern={event.pattern_id} rule={event.rule} outcome={outcome.status} "
        f"combo={event.priority_combination_id or '-'} conditions=[{conditions}] "
        f"{anchor_spans}"
        f"direction={plan.direction} entry_rule={plan.entry_rule!r} "
        f"reference_time={format_utc_plus_8(plan.structure_anchor.timestamp)} "
        f"reference_price_source={plan.reference_price_source} "
        f"reference_price={plan.entry_price:.8f} "
        f"entry_time={format_utc_plus_8(plan.entry_anchor.timestamp)} "
        f"entry={plan.entry_price:.8f} "
        f"anchor_geometry={plan.structure_anchor.price:.8f} "
        f"stop={plan.stop_price:.8f} lock_trigger={plan.lock_trigger_price:.8f} "
        f"locked_stop={plan.locked_stop_price:.8f} target={plan.target_price:.8f} "
        f"lock_time={lock_time} exit_time={exit_time} "
        f"bars_held={outcome.bars_held if outcome.bars_held is not None else '-'} "
        f"net_return_after_cost={net} simultaneous={outcome.simultaneous_touch} "
        f"detected_time={format_utc_plus_8(event.detected_timestamp)} "
        f"confirmation_delay_bars={plan.confirmation_delay_bars} "
        f"entry_wait_bars={plan.entry_wait_bars} "
        f"causal_at_entry={plan.causal_at_entry}"
    )


def _anchor_span_fields(event: PatternScanEvent) -> str:
    """Return explicit P1/P2/P3 bar spans for three-point support trades."""

    if event.pattern_id != "PATTERN_003" or len(event.anchors) != 3:
        return ""
    p1, p2, p3 = event.anchors
    return (
        f"p1_p2_span_bars={p2.index - p1.index} "
        f"p2_p3_span_bars={p3.index - p2.index} "
        f"p1_p3_span_bars={p3.index - p1.index} "
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
        "reason=unconfirmed/misaligned final pivot or no post-confirmation "
        "limit fill within six bars"
    )


def _time(value: int | str | None) -> str:
    return format_utc_plus_8(value) if value is not None else "-"
