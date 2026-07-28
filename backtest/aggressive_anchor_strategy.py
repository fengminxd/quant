"""Independent confirmed-pivot limit-entry and outcome evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from backtest.aggressive_entries import (
    aggressive_entry_definition,
    first_limit_fill,
    reference_confirmation_index,
    reference_order_price,
)
from backtest.aggressive_exit import resolve_aggressive_exit
from core.models import Bar
from core.pattern_policy import is_trade_event_enabled
from features.trade_feasibility import TransactionCostModel
from features.trade_plan import TradeDirection
from research.pattern_events import PatternAnchor, PatternScanEvent

AggressiveOutcomeStatus = Literal[
    "take_profit", "protected_profit", "stop_loss", "unresolved"
]


@dataclass(frozen=True)
class AggressiveTradePlan:
    """Limit entry derived from a confirmed pattern-specific pivot anchor."""

    event: PatternScanEvent
    direction: TradeDirection
    structure_anchor: PatternAnchor
    entry_anchor: PatternAnchor
    entry_price: float
    stop_price: float
    lock_trigger_price: float
    locked_stop_price: float
    target_price: float
    detected_index: int
    entry_rule: str
    reference_price_source: str
    trend_score: float | None = None

    @property
    def confirmation_delay_bars(self) -> int:
        """Bars between the reference anchor and structure detection."""

        return self.detected_index - self.structure_anchor.index

    @property
    def entry_wait_bars(self) -> int:
        """Closed candles waited after pivot confirmation for the limit fill."""

        return self.entry_anchor.index - self.detected_index

    @property
    def causal_at_entry(self) -> bool:
        """Whether entry occurs only after the structure confirmation close."""

        return self.confirmation_delay_bars >= 0 and self.entry_wait_bars >= 1


@dataclass(frozen=True)
class AggressiveTradeOutcome:
    """First terminal barrier reached under the aggressive stop state machine."""

    plan: AggressiveTradePlan
    status: AggressiveOutcomeStatus
    exit_index: int | None = None
    exit_timestamp: int | str | None = None
    exit_price: float | None = None
    bars_held: int | None = None
    lock_timestamp: int | str | None = None
    simultaneous_touch: bool = False
    net_return: float | None = None


@dataclass(frozen=True)
class AggressiveTradeSummary:
    """Outcome counts for one aggressive strategy cohort."""

    total: int
    take_profit: int
    protected_profit: int
    stop_loss: int
    unresolved: int

    @property
    def resolved(self) -> int:
        return self.take_profit + self.protected_profit + self.stop_loss

    @property
    def profitable(self) -> int:
        return self.take_profit + self.protected_profit

    def percentage(self, count: int) -> float:
        return 100.0 * count / self.total if self.total else 0.0

    def resolved_percentage(self, count: int) -> float:
        return 100.0 * count / self.resolved if self.resolved else 0.0


class AggressiveAnchorStrategyEvaluator:
    """Evaluate confirmed-pivot limit entries without prior report artifacts."""

    def __init__(
        self,
        stop_loss_ratio: float = 0.015,
        lock_trigger_ratio: float = 0.015,
        take_profit_ratio: float = 0.03,
        max_entry_wait_bars: int = 6,
        costs: TransactionCostModel | None = None,
    ) -> None:
        ratios = (stop_loss_ratio, lock_trigger_ratio, take_profit_ratio)
        if any(not 0.0 < ratio < 1.0 for ratio in ratios):
            raise ValueError("strategy ratios must be between zero and one")
        if not stop_loss_ratio < take_profit_ratio:
            raise ValueError("stop loss must be below take profit")
        if not lock_trigger_ratio < take_profit_ratio:
            raise ValueError("lock trigger must be below take profit")
        if max_entry_wait_bars <= 0:
            raise ValueError("max_entry_wait_bars must be positive")
        self.stop_loss_ratio = stop_loss_ratio
        self.lock_trigger_ratio = lock_trigger_ratio
        self.take_profit_ratio = take_profit_ratio
        self.max_entry_wait_bars = max_entry_wait_bars
        self.costs = costs or TransactionCostModel()

    def evaluate(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> AggressiveTradeOutcome | None:
        """Build and evaluate one eligible directional structure."""

        plan = self.plan(event, bars)
        return self.evaluate_plan(plan, bars) if plan is not None else None

    def plan(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> AggressiveTradePlan | None:
        """Map a confirmed reference pivot to its first six-bar limit fill."""

        if not is_trade_event_enabled(
            event.pattern_id,
            event.priority_combination_id,
        ):
            return None
        definition = aggressive_entry_definition(event, bars)
        if definition is None:
            return None
        direction = definition.direction
        anchor = definition.anchor
        if not 0 <= anchor.index < len(bars):
            raise ValueError("entry anchor is outside supplied bars")
        detected_index = _timestamp_index(bars, event.detected_timestamp)
        confirmation_index = reference_confirmation_index(definition)
        if (
            confirmation_index >= len(bars)
            or detected_index != confirmation_index
        ):
            return None
        reference = reference_order_price(bars[anchor.index], direction)
        entry, price_source = reference
        fill = first_limit_fill(
            bars,
            confirmation_index,
            direction,
            entry,
            self.max_entry_wait_bars,
        )
        if fill is None:
            return None
        if direction == "bullish":
            stop = entry * (1.0 - self.stop_loss_ratio)
            lock = entry * (1.0 + self.lock_trigger_ratio)
            target = entry * (1.0 + self.take_profit_ratio)
        else:
            stop = entry * (1.0 + self.stop_loss_ratio)
            lock = entry * (1.0 - self.lock_trigger_ratio)
            target = entry * (1.0 - self.take_profit_ratio)
        return AggressiveTradePlan(
            event,
            direction,
            anchor,
            fill,
            entry,
            stop,
            lock,
            lock,
            target,
            detected_index,
            definition.rule,
            price_source,
            definition.trend_score,
        )

    def evaluate_plan(
        self,
        plan: AggressiveTradePlan,
        bars: Sequence[Bar],
    ) -> AggressiveTradeOutcome:
        """Run the independent stop, profit lock, and final target state machine."""

        resolved = resolve_aggressive_exit(
            plan.direction,
            plan.stop_price,
            plan.lock_trigger_price,
            plan.locked_stop_price,
            plan.target_price,
            bars,
            plan.entry_anchor.index,
        )
        index = resolved.index
        price = resolved.price
        return AggressiveTradeOutcome(
            plan=plan,
            status=resolved.status,
            exit_index=index,
            exit_timestamp=bars[index].timestamp if index is not None else None,
            exit_price=price,
            bars_held=(
                index - plan.entry_anchor.index if index is not None else None
            ),
            lock_timestamp=resolved.lock_timestamp,
            simultaneous_touch=resolved.simultaneous_touch,
            net_return=(
                self._net_return(plan, price) if price is not None else None
            ),
        )

    def _net_return(self, plan: AggressiveTradePlan, exit_price: float) -> float:
        gross = (
            (exit_price - plan.entry_price) / plan.entry_price
            if plan.direction == "bullish"
            else (plan.entry_price - exit_price) / plan.entry_price
        )
        execution = (
            self.costs.entry_fee_rate
            + self.costs.exit_fee_rate
            + 2.0 * self.costs.slippage_rate_per_side
        )
        return gross - execution - self.costs.funding_rate


def summarize_aggressive_outcomes(
    outcomes: Sequence[AggressiveTradeOutcome],
) -> AggressiveTradeSummary:
    """Summarize outcomes without dropping unresolved trades."""

    return AggressiveTradeSummary(
        len(outcomes),
        sum(item.status == "take_profit" for item in outcomes),
        sum(item.status == "protected_profit" for item in outcomes),
        sum(item.status == "stop_loss" for item in outcomes),
        sum(item.status == "unresolved" for item in outcomes),
    )


def _timestamp_index(bars: Sequence[Bar], timestamp: int | str) -> int:
    indexes = {bar.timestamp: index for index, bar in enumerate(bars)}
    if timestamp not in indexes:
        raise ValueError("event detection timestamp is outside supplied bars")
    return indexes[timestamp]
