"""Plain-text reporting for retrospective Pattern anchor outcomes."""

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
    """Evaluate the PDF cohort and write a UTF-8 text report without redrawing."""

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
            f"FIXED_COMBO 未满足入场趋势/锚点条件: {len(fixed_excluded)}",
            "",
        )
    )
    for status, title in (
        ("stop_loss", "止损案例"),
        ("take_profit", "止盈案例"),
        ("unresolved", "截至数据末尾未触发案例"),
    ):
        selected = [outcome for outcome in outcomes if outcome.status == status]
        lines.extend((f"=== {title} ({len(selected)}) ===",))
        lines.extend(_outcome_line(outcome) for outcome in selected)
        lines.append("")
    lines.append(f"=== 不满足入场规则的 PDF 案例 ({len(excluded)}) ===")
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
    causal_count = sum(outcome.plan.causal_at_anchor for outcome in outcomes)
    simultaneous = sum(outcome.simultaneous_touch for outcome in outcomes)
    cohort = (
        f"{events[0].symbol} {events[0].timeframe}"
        if events
        else "Empty"
    )
    return [
        f"{cohort} Pattern 锚点交易结果统计",
        f"来源 PDF: {source_pdf}",
        f"PDF 去重案例数: {len(events)}",
        f"符合指定入场规则: {len(outcomes)}",
        f"不满足三角趋势/第三锚点条件: {len(excluded)}",
        "",
        "统计口径:",
        "- 入场价为规则指定的几何锚点价格。",
        "- 从锚点后的下一根 K 线开始检查，不使用入场锚点 K 线内未知路径。",
        "- 多单止损/止盈为入场价 -/+1.5%；空单方向相反。",
        "- 同一根 K 线同时触发止损和止盈时，按保守原则计为止损。",
        "- 未决案例计入总案例分母；同时另列仅已平仓案例占比。",
        "- 三角趋势冻结在最早边界锚点，沿用 FIXED_COMBO 趋势结构门槛。",
        (
            "- 成本估计: 单边手续费 "
            f"{costs.fee_rate_per_side:.4%}，单边滑点 "
            f"{costs.slippage_rate_per_side:.4%}，资金费 "
            f"{costs.funding_rate:.4%}。"
        ),
        (
            "- 这是回顾性锚点结果标签，不是可实时执行回测；完整 Pattern "
            "通常在锚点后才确认。"
        ),
        f"- 锚点当时已因果可知的案例: {causal_count}/{len(outcomes)}",
        f"- 同根 K 线双触发并按止损处理: {simultaneous}",
        "",
    ]


def _summary_lines(title: str, summary: AnchorTradeSummary) -> list[str]:
    return [
        f"=== {title} ===",
        f"总案例: {summary.total}",
        (
            f"止盈: {summary.take_profit} "
            f"({summary.percentage(summary.take_profit):.2f}% / 全部案例)"
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
            f"仅已平仓占比: 止盈 "
            f"{summary.resolved_percentage(summary.take_profit):.2f}%，止损 "
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
    return (
        f"symbol={event.symbol} timeframe={event.timeframe} "
        f"pattern={event.pattern_id} rule={event.rule} outcome={outcome.status} "
        f"combo={combo} "
        f"conditions=[{conditions}] direction={plan.direction} "
        f"entry_rule={plan.entry_rule!r} "
        f"entry_time={format_utc_plus_8(plan.entry_anchor.timestamp)} "
        f"entry={plan.entry_price:.8f} stop={plan.stop_price:.8f} "
        f"target={plan.target_price:.8f} exit_time={exit_time} "
        f"bars_held={outcome.bars_held if outcome.bars_held is not None else '-'} "
        f"net_return_after_cost={net} simultaneous={outcome.simultaneous_touch} "
        f"detected_time={format_utc_plus_8(event.detected_timestamp)} "
        f"confirmation_delay_bars={plan.confirmation_delay_bars} "
        f"causal_at_anchor={plan.causal_at_anchor}"
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
        "reason=no frozen up/down trend with corresponding third boundary anchor"
    )
