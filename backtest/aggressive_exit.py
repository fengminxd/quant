"""Independent exit state machine for filled aggressive limit entries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Bar
from features.trade_plan import TradeDirection


@dataclass(frozen=True)
class AggressiveExitResolution:
    """Terminal or unresolved state after a filled aggressive entry."""

    status: Literal[
        "take_profit", "protected_profit", "stop_loss", "unresolved"
    ]
    index: int | None
    price: float | None
    lock_timestamp: int | str | None
    simultaneous_touch: bool


def resolve_aggressive_exit(
    direction: TradeDirection,
    stop_price: float,
    lock_trigger_price: float,
    locked_stop_price: float,
    target_price: float,
    bars: Sequence[Bar],
    entry_index: int,
) -> AggressiveExitResolution:
    """Resolve exits from the candle after the limit fill."""

    locked = False
    lock_timestamp: int | str | None = None
    for index in range(entry_index + 1, len(bars)):
        bar = bars[index]
        if not locked:
            stop, trigger, target = _initial_touches(
                direction, stop_price, lock_trigger_price, target_price, bar
            )
            if stop:
                return AggressiveExitResolution(
                    "stop_loss",
                    index,
                    stop_price,
                    lock_timestamp,
                    trigger or target,
                )
            if target:
                return AggressiveExitResolution(
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
            return AggressiveExitResolution(
                "protected_profit",
                index,
                locked_stop_price,
                lock_timestamp,
                target,
            )
        if target:
            return AggressiveExitResolution(
                "take_profit",
                index,
                target_price,
                lock_timestamp,
                False,
            )
    return AggressiveExitResolution(
        "unresolved", None, None, lock_timestamp, False
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
