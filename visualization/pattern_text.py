"""Human-readable PDF descriptions for Pattern and fixed-combination evidence."""

from __future__ import annotations

from textwrap import wrap

from research.pattern_events import PatternScanEvent


CONDITION_LABELS = {
    "second_anchor_close_above_ema99": "P2 close > EMA99",
    "second_anchor_open_below_ema99": "P2 open < EMA99",
    "head_close_above_ema99": "Head close > EMA99",
    "head_double_bottom_support": "Head + prior anchor = double-bottom support",
    "head_open_below_ema99": "Head open < EMA99",
    "head_horizontal_resistance": "Head + prior anchor = horizontal resistance",
    "first_anchor_double_bottom_support": "P1 + prior anchor = double-bottom support",
    "all_three_anchors_close_above_ema99": "P1/P2/P3 closes > EMA99",
    "third_anchor_breakout_retest_support": (
        "P3 + prior anchor = breakout-retest support"
    ),
    "first_anchor_horizontal_resistance": (
        "P1 + prior anchor = horizontal resistance"
    ),
    "third_anchor_open_below_ema99": "P3 open < EMA99",
    "lower_first_anchor_double_bottom_support": (
        "Lower P1 + prior anchor = double-bottom support"
    ),
    "lower_third_anchor_close_above_ema99": "Lower P3 close > EMA99",
    "upper_first_anchor_horizontal_resistance": (
        "Upper P1 + prior anchor = horizontal resistance"
    ),
    "upper_third_anchor_open_below_ema99": "Upper P3 open < EMA99",
}


def condition_label(condition: str) -> str:
    """Return a stable readable label without hiding unknown evidence names."""

    return CONDITION_LABELS.get(condition, condition.replace("_", " "))


def event_title(event: PatternScanEvent, width: int = 92) -> str:
    """Build the complete per-event PDF explanation."""

    lines = [
        f"Symbol: {event.symbol} | Timeframe: {event.timeframe}",
        f"Rule: {event.pattern_id} / {event.rule}",
    ]
    if event.priority_fixed_combination:
        conditions = "; ".join(
            condition_label(name) for name in event.priority_matched_conditions
        )
        lines.append(
            f"Fixed combination: {event.priority_combination_id} "
            f"(coverage {event.priority_combination_score:.0f})"
        )
        lines.extend(
            wrap(
                f"Combined conditions ({len(event.priority_matched_conditions)}): "
                f"{conditions or '-'}",
                width=width,
                subsequent_indent="  ",
            )
        )
    lines.append(f"Pattern: {event.pattern_name} | score {event.score:.2f}")
    return "\n".join(lines)


def level_relation_kind(rule_type: str) -> tuple[str, str, str]:
    """Return marker prefix, readable relation name, and plot color."""

    if "resistance" in rule_type:
        return "R", "horizontal resistance", "#c62828"
    if rule_type == "breakout_retest":
        return "S", "breakout-retest support", "#2e7d32"
    return "S", "double-bottom support", "#2e7d32"
