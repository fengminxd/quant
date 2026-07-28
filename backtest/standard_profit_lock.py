"""Exit state machine for the standard report's profit-lock strategy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Bar
from features.trade_plan import TradeDirection


@dataclass(frozen=True)
class StandardExitResolution:
    """One terminal exit after initial-stop or locked-profit processing."""

    status: Literal[
        "take_profit", "protected_profit", "stop_loss", "unresolved"
    ]
    index: int | None
    price: float | None
    lock_timestamp: int | str | None
    simultaneous_touch: bool


def resolve_standard_exit(
    direction: TradeDirection,
    stop_price: float,
    lock_trigger_price: float,
    locked_stop_price: float,
    target_price: float,
    bars: Sequence[Bar],
    entry_index: int,
) -> StandardExitResolution:
    """Resolve barriers conservatively without assuming intrabar order."""

    locked = False
    lock_timestamp: int | str | None = None
    for index in range(entry_index + 1, len(bars)):
        bar = bars[index]
        if not locked:
            stop, trigger, target = _initial_touches(
                direction,
                stop_price,
                lock_trigger_price,
                target_price,
                bar,
            )
            if stop:
                return StandardExitResolution(
                    "stop_loss",
                    index,
                    stop_price,
                    lock_timestamp,
                    trigger or target,
                )
            if target:
                return StandardExitResolution(
                    "take_profit",
                    index,
                    target_price,
                    bar.timestamp,
                    False,
                )
            if trigger:
                locked = True
                lock_timestamp = bar.timestamp
            continue
        protected, target = _locked_touches(
            direction, locked_stop_price, target_price, bar
        )
        if protected:
            return StandardExitResolution(
                "protected_profit",
                index,
                locked_stop_price,
                lock_timestamp,
                target,
            )
        if target:
            return StandardExitResolution(
                "take_profit",
                index,
                target_price,
                lock_timestamp,
                False,
            )
    return StandardExitResolution(
        "unresolved",
        None,
        None,
        lock_timestamp,
        False,
    )


def _initial_touches(
    direction: TradeDirection,
    stop: float,
    trigger: float,
    target: float,
    bar: Bar,
) -> tuple[bool, bool, bool]:
    if direction == "bullish":
        return bar.low <= stop, bar.high >= trigger, bar.high >= target
    return bar.high >= stop, bar.low <= trigger, bar.low <= target


def _locked_touches(
    direction: TradeDirection,
    protected: float,
    target: float,
    bar: Bar,
) -> tuple[bool, bool]:
    if direction == "bullish":
        return bar.low <= protected, bar.high >= target
    return bar.high >= protected, bar.low <= target
