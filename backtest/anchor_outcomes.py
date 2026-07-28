"""Causal outcomes for standard Pattern structure-retest entries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Bar
from backtest.causal_anchor_entries import CausalAnchorEntryResolver
from backtest.standard_profit_lock import resolve_standard_exit
from features.trade_feasibility import TransactionCostModel
from features.trade_plan import TradeDirection
from research.pattern_events import PatternAnchor, PatternScanEvent

OutcomeStatus = Literal[
    "take_profit", "protected_profit", "stop_loss", "unresolved"
]


@dataclass(frozen=True)
class AnchorTradePlan:
    """One causal reclaim entry with configurable percentage barriers."""

    event: PatternScanEvent
    direction: TradeDirection
    entry_anchor: PatternAnchor
    entry_price: float
    stop_price: float
    target_price: float
    entry_rule: str
    detected_index: int
    trend_score: float | None = None
    structure_anchor: PatternAnchor | None = None
    entry_quality_score: float | None = None
    lock_trigger_price: float | None = None
    locked_stop_price: float | None = None

    @property
    def confirmation_delay_bars(self) -> int:
        """Return how many bars after the anchor the Pattern became known."""

        anchor = self.structure_anchor or self.entry_anchor
        return self.detected_index - anchor.index

    @property
    def causal_at_anchor(self) -> bool:
        """Whether the complete Pattern was already known at the entry anchor."""

        return self.confirmation_delay_bars <= 0

    @property
    def entry_wait_bars(self) -> int:
        """Return closed bars waited after Pattern detection."""

        return self.entry_anchor.index - self.detected_index

    @property
    def causal_at_entry(self) -> bool:
        """Whether the entry occurs no earlier than Pattern detection."""

        return self.entry_wait_bars >= 0


@dataclass(frozen=True)
class AnchorTradeOutcome:
    """First barrier touched after one causal reclaim entry."""

    plan: AnchorTradePlan
    status: OutcomeStatus
    exit_index: int | None = None
    exit_timestamp: int | str | None = None
    exit_price: float | None = None
    bars_held: int | None = None
    simultaneous_touch: bool = False
    net_return: float | None = None
    lock_timestamp: int | str | None = None


@dataclass(frozen=True)
class AnchorTradeSummary:
    """Counts and percentages over one explicit outcome cohort."""

    total: int
    take_profit: int
    protected_profit: int
    stop_loss: int
    unresolved: int

    def percentage(self, count: int) -> float:
        """Return a percentage using every eligible case as denominator."""

        return 100.0 * count / self.total if self.total else 0.0

    @property
    def resolved(self) -> int:
        return self.take_profit + self.protected_profit + self.stop_loss

    @property
    def profitable(self) -> int:
        """Return all exits closed above the cost-unadjusted entry."""

        return self.take_profit + self.protected_profit

    def resolved_percentage(self, count: int) -> float:
        """Return a percentage using only closed cases as denominator."""

        return 100.0 * count / self.resolved if self.resolved else 0.0


class AnchorTradeOutcomeEvaluator:
    """Resolve standard entries with initial stop, profit lock, and final target."""

    def __init__(
        self,
        barrier_ratio: float = 0.015,
        costs: TransactionCostModel | None = None,
        *,
        stop_loss_ratio: float | None = None,
        lock_trigger_ratio: float = 0.015,
        take_profit_ratio: float = 0.03,
        entry_resolver: CausalAnchorEntryResolver | None = None,
    ) -> None:
        if not 0.0 < barrier_ratio < 1.0:
            raise ValueError("barrier_ratio must be between zero and one")
        stop_ratio = barrier_ratio if stop_loss_ratio is None else stop_loss_ratio
        target_ratio = take_profit_ratio
        if not 0.0 < stop_ratio < 1.0:
            raise ValueError("stop_loss_ratio must be between zero and one")
        if not 0.0 < target_ratio < 1.0:
            raise ValueError("take_profit_ratio must be between zero and one")
        if not 0.0 < lock_trigger_ratio < 1.0:
            raise ValueError("lock_trigger_ratio must be between zero and one")
        if lock_trigger_ratio >= target_ratio:
            raise ValueError("lock_trigger_ratio must be below take_profit_ratio")
        self.barrier_ratio = barrier_ratio
        self.stop_loss_ratio = stop_ratio
        self.lock_trigger_ratio = lock_trigger_ratio
        self.take_profit_ratio = target_ratio
        self.costs = costs or TransactionCostModel()
        self.entry_resolver = entry_resolver or CausalAnchorEntryResolver()

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
        """Map one event to the first eligible post-detection reclaim."""

        if not bars:
            raise ValueError("at least one bar is required")
        detected_index = _timestamp_index(bars, event.detected_timestamp)
        resolved = self.entry_resolver.resolve(event, bars, detected_index)
        if resolved is None:
            return None
        entry = float(resolved.entry_anchor.price)
        if entry <= 0.0:
            raise ValueError("entry price must be positive")
        if resolved.direction == "bullish":
            stop = entry * (1.0 - self.stop_loss_ratio)
            lock_trigger = entry * (1.0 + self.lock_trigger_ratio)
            target = entry * (1.0 + self.take_profit_ratio)
        else:
            stop = entry * (1.0 + self.stop_loss_ratio)
            lock_trigger = entry * (1.0 - self.lock_trigger_ratio)
            target = entry * (1.0 - self.take_profit_ratio)
        return AnchorTradePlan(
            event=event,
            direction=resolved.direction,
            entry_anchor=resolved.entry_anchor,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            entry_rule=resolved.rule,
            detected_index=detected_index,
            trend_score=resolved.trend_score,
            structure_anchor=resolved.structure_anchor,
            entry_quality_score=resolved.entry_quality_score,
            lock_trigger_price=lock_trigger,
            locked_stop_price=lock_trigger,
        )

    def evaluate_plan(
        self,
        plan: AnchorTradePlan,
        bars: Sequence[Bar],
    ) -> AnchorTradeOutcome:
        """Use later OHLC bars and activate the profit lock next-bar."""

        lock_trigger = plan.lock_trigger_price
        locked_stop = plan.locked_stop_price
        if lock_trigger is None:
            multiplier = (
                1.0 + self.lock_trigger_ratio
                if plan.direction == "bullish"
                else 1.0 - self.lock_trigger_ratio
            )
            lock_trigger = plan.entry_price * multiplier
        if locked_stop is None:
            locked_stop = lock_trigger
        resolution = resolve_standard_exit(
            direction=plan.direction,
            stop_price=plan.stop_price,
            lock_trigger_price=lock_trigger,
            locked_stop_price=locked_stop,
            target_price=plan.target_price,
            bars=bars,
            entry_index=plan.entry_anchor.index,
        )
        index = resolution.index
        exit_price = resolution.price
        return AnchorTradeOutcome(
            plan=plan,
            status=resolution.status,
            exit_index=index,
            exit_timestamp=bars[index].timestamp if index is not None else None,
            exit_price=exit_price,
            bars_held=(
                index - plan.entry_anchor.index if index is not None else None
            ),
            simultaneous_touch=resolution.simultaneous_touch,
            net_return=(
                self._net_return(plan, exit_price)
                if exit_price is not None
                else None
            ),
            lock_timestamp=resolution.lock_timestamp,
        )

    def _net_return(self, plan: AnchorTradePlan, exit_price: float) -> float:
        gross = (
            (exit_price - plan.entry_price) / plan.entry_price
            if plan.direction == "bullish"
            else (plan.entry_price - exit_price) / plan.entry_price
        )
        execution_cost = (
            self.costs.entry_fee_rate
            + self.costs.exit_fee_rate
            + 2.0 * self.costs.slippage_rate_per_side
        )
        return gross - execution_cost - self.costs.funding_rate


def summarize_outcomes(
    outcomes: Sequence[AnchorTradeOutcome],
) -> AnchorTradeSummary:
    """Summarize an explicit cohort without dropping unresolved cases."""

    return AnchorTradeSummary(
        len(outcomes),
        sum(outcome.status == "take_profit" for outcome in outcomes),
        sum(outcome.status == "protected_profit" for outcome in outcomes),
        sum(outcome.status == "stop_loss" for outcome in outcomes),
        sum(outcome.status == "unresolved" for outcome in outcomes),
    )


def _timestamp_index(bars: Sequence[Bar], timestamp: int | str) -> int:
    indexes = {bar.timestamp: index for index, bar in enumerate(bars)}
    if timestamp not in indexes:
        raise ValueError("event detection timestamp is outside supplied bars")
    return indexes[timestamp]
