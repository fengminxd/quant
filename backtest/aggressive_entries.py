"""Confirmed-pivot anchor references and delayed fills for aggressive reports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.models import Bar
from features.context import ContextFeatureExtractor, directional_structure_score
from features.trade_plan import TradeDirection
from indicators.swing import PivotKind
from research.pattern_events import PatternAnchor, PatternScanEvent


@dataclass(frozen=True)
class AggressiveEntryDefinition:
    """Pattern-specific reference anchor and its causal pivot confirmation."""

    direction: TradeDirection
    anchor: PatternAnchor
    rule: str
    pivot_kind: PivotKind
    confirmation_bars: int
    trend_score: float | None = None


def aggressive_entry_definition(
    event: PatternScanEvent,
    bars: Sequence[Bar],
) -> AggressiveEntryDefinition | None:
    """Resolve the requested reference anchor and direction."""

    group = event.anchor_groups[0] if event.anchor_groups else event.anchors
    definitions: dict[
        str, tuple[TradeDirection, int, str, PivotKind, int]
    ] = {
        "PATTERN_003": (
            "bullish",
            2,
            "third trendline-support anchor",
            "low",
            2,
        ),
        "PATTERN_004": (
            "bullish",
            1,
            "second horizontal-support anchor",
            "low",
            5,
        ),
        "PATTERN_006": (
            "bearish",
            1,
            "second horizontal-resistance anchor",
            "high",
            2,
        ),
        "PATTERN_007": ("bullish", 2, "right-shoulder anchor", "low", 5),
        "PATTERN_008": ("bearish", 2, "right-shoulder anchor", "high", 5),
    }
    defined = definitions.get(event.pattern_id)
    if defined is not None:
        direction, position, rule, pivot_kind, confirmation_bars = defined
        ordered = sorted(group, key=lambda anchor: anchor.index)
        if len(ordered) <= position:
            return None
        return AggressiveEntryDefinition(
            direction,
            ordered[position],
            rule,
            pivot_kind,
            confirmation_bars,
        )
    if event.pattern_id != "PATTERN_002" or len(event.anchor_groups) < 2:
        return None
    upper = sorted(event.anchor_groups[0], key=lambda anchor: anchor.index)
    lower = sorted(event.anchor_groups[1], key=lambda anchor: anchor.index)
    first_index = min(anchor.index for anchor in (*upper, *lower))
    context = ContextFeatureExtractor().extract(bars[: first_index + 1])
    up_score, _, uptrend = directional_structure_score(context, bullish=True)
    down_score, _, downtrend = directional_structure_score(
        context, bullish=False
    )
    candidates: list[AggressiveEntryDefinition] = []
    if uptrend and len(lower) >= 3:
        candidates.append(
            AggressiveEntryDefinition(
                "bullish",
                lower[2],
                "uptrend lower-boundary P3",
                "low",
                2,
                up_score,
            )
        )
    if downtrend and len(upper) >= 3:
        candidates.append(
            AggressiveEntryDefinition(
                "bearish",
                upper[2],
                "downtrend upper-boundary P3",
                "high",
                2,
                down_score,
            )
        )
    return (
        max(candidates, key=lambda item: item.trend_score or 0.0)
        if candidates
        else None
    )


def reference_confirmation_index(
    definition: AggressiveEntryDefinition,
) -> int:
    """Return the first close where the final pivot is causally confirmed."""

    return definition.anchor.index + definition.confirmation_bars


def reference_order_price(
    bar: Bar,
    direction: TradeDirection,
) -> tuple[float, str]:
    """Select the aggressive anchor price from body-shadow geometry.

    A doji uses the entry-side extreme. Otherwise, a shadow no longer than
    the body also uses that extreme; a longer shadow uses the entry-side
    candle-body edge.
    """

    if bar.close == bar.open:
        return (
            (bar.low, "doji_low")
            if direction == "bullish"
            else (bar.high, "doji_high")
        )
    body = abs(bar.close - bar.open)
    if direction == "bullish":
        lower_shadow = min(bar.open, bar.close) - bar.low
        if lower_shadow <= body:
            return bar.low, "lower_shadow_not_longer_low"
        if bar.close > bar.open:
            return bar.open, "lower_shadow_long_bullish_open"
        return bar.close, "lower_shadow_long_bearish_close"
    upper_shadow = bar.high - max(bar.open, bar.close)
    if upper_shadow <= body:
        return bar.high, "upper_shadow_not_longer_high"
    if bar.close > bar.open:
        return bar.close, "upper_shadow_long_bullish_close"
    return bar.open, "upper_shadow_long_bearish_open"


def first_limit_fill(
    bars: Sequence[Bar],
    reference_index: int,
    direction: TradeDirection,
    price: float,
    max_wait_bars: int,
) -> PatternAnchor | None:
    """Find the first post-confirmation limit fill before the sixth close."""

    final_index = min(len(bars) - 1, reference_index + max_wait_bars)
    for index in range(reference_index + 1, final_index + 1):
        bar = bars[index]
        touched = bar.low <= price if direction == "bullish" else bar.high >= price
        if touched:
            return PatternAnchor(index, bar.timestamp, price)
    return None
