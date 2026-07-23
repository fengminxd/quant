"""Retrospective outcomes for explicitly requested Pattern anchor entries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Bar
from features.context import ContextFeatureExtractor, directional_structure_score
from features.trade_feasibility import TransactionCostModel
from features.trade_plan import TradeDirection
from research.pattern_events import PatternAnchor, PatternScanEvent

OutcomeStatus = Literal["take_profit", "stop_loss", "unresolved"]


@dataclass(frozen=True)
class AnchorTradePlan:
    """One retrospective anchor entry with symmetric percentage barriers."""

    event: PatternScanEvent
    direction: TradeDirection
    entry_anchor: PatternAnchor
    entry_price: float
    stop_price: float
    target_price: float
    entry_rule: str
    detected_index: int
    trend_score: float | None = None

    @property
    def confirmation_delay_bars(self) -> int:
        """Return how many bars after the anchor the Pattern became known."""

        return self.detected_index - self.entry_anchor.index

    @property
    def causal_at_anchor(self) -> bool:
        """Whether the complete Pattern was already known at the entry anchor."""

        return self.confirmation_delay_bars <= 0


@dataclass(frozen=True)
class AnchorTradeOutcome:
    """First barrier touched after one retrospective anchor entry."""

    plan: AnchorTradePlan
    status: OutcomeStatus
    exit_index: int | None = None
    exit_timestamp: int | str | None = None
    exit_price: float | None = None
    bars_held: int | None = None
    simultaneous_touch: bool = False
    net_return: float | None = None


@dataclass(frozen=True)
class AnchorTradeSummary:
    """Counts and percentages over one explicit outcome cohort."""

    total: int
    take_profit: int
    stop_loss: int
    unresolved: int

    def percentage(self, count: int) -> float:
        """Return a percentage using every eligible case as denominator."""

        return 100.0 * count / self.total if self.total else 0.0

    @property
    def resolved(self) -> int:
        return self.take_profit + self.stop_loss

    def resolved_percentage(self, count: int) -> float:
        """Return a percentage using only closed cases as denominator."""

        return 100.0 * count / self.resolved if self.resolved else 0.0


class AnchorTradeOutcomeEvaluator:
    """Resolve requested anchor rules and label the first ± barrier touch."""

    def __init__(
        self,
        barrier_ratio: float = 0.015,
        costs: TransactionCostModel | None = None,
    ) -> None:
        if not 0.0 < barrier_ratio < 1.0:
            raise ValueError("barrier_ratio must be between zero and one")
        self.barrier_ratio = barrier_ratio
        self.costs = costs or TransactionCostModel()

    def evaluate(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> AnchorTradeOutcome | None:
        """Return one outcome, or None when no requested entry rule applies."""

        plan = self.plan(event, bars)
        return self.evaluate_plan(plan, bars) if plan is not None else None

    def plan(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> AnchorTradePlan | None:
        """Map one PDF event to the requested Pattern-specific anchor."""

        if not bars:
            raise ValueError("at least one bar is required")
        direction, anchor, rule, trend_score = self._entry_definition(event, bars)
        if direction is None or anchor is None or rule is None:
            return None
        if not 0 <= anchor.index < len(bars):
            raise ValueError("entry anchor is outside supplied bars")
        detected_index = _timestamp_index(bars, event.detected_timestamp)
        entry = float(anchor.price)
        if entry <= 0.0:
            raise ValueError("entry price must be positive")
        if direction == "bullish":
            stop = entry * (1.0 - self.barrier_ratio)
            target = entry * (1.0 + self.barrier_ratio)
        else:
            stop = entry * (1.0 + self.barrier_ratio)
            target = entry * (1.0 - self.barrier_ratio)
        return AnchorTradePlan(
            event,
            direction,
            anchor,
            entry,
            stop,
            target,
            rule,
            detected_index,
            trend_score,
        )

    def evaluate_plan(
        self,
        plan: AnchorTradePlan,
        bars: Sequence[Bar],
    ) -> AnchorTradeOutcome:
        """Use later OHLC bars; same-bar dual touches resolve stop-first."""

        for index in range(plan.entry_anchor.index + 1, len(bars)):
            bar = bars[index]
            stop_touch, target_touch = _barrier_touches(plan, bar)
            if not stop_touch and not target_touch:
                continue
            stopped = stop_touch
            status: OutcomeStatus = "stop_loss" if stopped else "take_profit"
            exit_price = plan.stop_price if stopped else plan.target_price
            return AnchorTradeOutcome(
                plan,
                status,
                index,
                bar.timestamp,
                exit_price,
                index - plan.entry_anchor.index,
                stop_touch and target_touch,
                self._net_return(plan, exit_price),
            )
        return AnchorTradeOutcome(plan, "unresolved")

    def _entry_definition(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> tuple[
        TradeDirection | None,
        PatternAnchor | None,
        str | None,
        float | None,
    ]:
        group = event.anchor_groups[0] if event.anchor_groups else event.anchors
        definitions: dict[str, tuple[TradeDirection, int, str]] = {
            "PATTERN_003": ("bullish", 2, "third trendline-support anchor"),
            "PATTERN_004": ("bullish", 1, "second horizontal-support anchor"),
            "PATTERN_005": ("bearish", 2, "third trendline-resistance anchor"),
            "PATTERN_006": ("bearish", 1, "second horizontal-resistance anchor"),
            "PATTERN_007": ("bullish", 2, "right-shoulder anchor"),
            "PATTERN_008": ("bearish", 2, "right-shoulder anchor"),
        }
        defined = definitions.get(event.pattern_id)
        if defined is not None:
            direction, position, rule = defined
            ordered = sorted(group, key=lambda anchor: anchor.index)
            anchor = ordered[position] if len(ordered) > position else None
            return direction, anchor, rule, None
        if event.pattern_id == "PATTERN_002":
            return self._triangle_entry(event, bars)
        return None, None, None, None

    @staticmethod
    def _triangle_entry(
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> tuple[
        TradeDirection | None,
        PatternAnchor | None,
        str | None,
        float | None,
    ]:
        if len(event.anchor_groups) < 2:
            return None, None, None, None
        upper = sorted(event.anchor_groups[0], key=lambda anchor: anchor.index)
        lower = sorted(event.anchor_groups[1], key=lambda anchor: anchor.index)
        first_anchor = min(anchor.index for anchor in (*upper, *lower))
        features = ContextFeatureExtractor().extract(bars[: first_anchor + 1])
        up_score, _, uptrend = directional_structure_score(features, bullish=True)
        down_score, _, downtrend = directional_structure_score(
            features, bullish=False
        )
        candidates: list[
            tuple[float, TradeDirection, PatternAnchor, str]
        ] = []
        if uptrend and len(lower) >= 3:
            candidates.append(
                (up_score, "bullish", lower[2], "uptrend lower-boundary P3")
            )
        if downtrend and len(upper) >= 3:
            candidates.append(
                (down_score, "bearish", upper[2], "downtrend upper-boundary P3")
            )
        if not candidates:
            return None, None, None, None
        score, direction, anchor, rule = max(candidates, key=lambda item: item[0])
        return direction, anchor, rule, score

    def _net_return(self, plan: AnchorTradePlan, exit_price: float) -> float:
        gross = (
            (exit_price - plan.entry_price) / plan.entry_price
            if plan.direction == "bullish"
            else (plan.entry_price - exit_price) / plan.entry_price
        )
        per_side = self.costs.fee_rate_per_side + self.costs.slippage_rate_per_side
        return gross - 2.0 * per_side - self.costs.funding_rate


def summarize_outcomes(
    outcomes: Sequence[AnchorTradeOutcome],
) -> AnchorTradeSummary:
    """Summarize an explicit cohort without dropping unresolved cases."""

    return AnchorTradeSummary(
        len(outcomes),
        sum(outcome.status == "take_profit" for outcome in outcomes),
        sum(outcome.status == "stop_loss" for outcome in outcomes),
        sum(outcome.status == "unresolved" for outcome in outcomes),
    )


def _barrier_touches(plan: AnchorTradePlan, bar: Bar) -> tuple[bool, bool]:
    if plan.direction == "bullish":
        return bar.low <= plan.stop_price, bar.high >= plan.target_price
    return bar.high >= plan.stop_price, bar.low <= plan.target_price


def _timestamp_index(bars: Sequence[Bar], timestamp: int | str) -> int:
    indexes = {bar.timestamp: index for index, bar in enumerate(bars)}
    if timestamp not in indexes:
        raise ValueError("event detection timestamp is outside supplied bars")
    return indexes[timestamp]
