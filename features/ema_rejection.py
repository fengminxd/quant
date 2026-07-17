"""Reusable causal EMA wick-rejection features."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from indicators.ema import exponential_moving_average


def upper_ema_wick_rejection_at_close(
    data: Sequence[Bar],
    ema_period: int = 99,
    *,
    initial_ema: float | None = None,
) -> bool:
    """Return whether the latest closed bar rejects EMA through its upper wick."""

    return bool(
        upper_ema_wick_rejection_indexes(
            data,
            ema_period,
            0,
            initial_ema=initial_ema,
        )
    )


def upper_ema_wick_rejection_indexes(
    data: Sequence[Bar],
    ema_period: int = 99,
    lookback_bars: int = 2,
    *,
    initial_ema: float | None = None,
) -> tuple[int, ...]:
    """Return recent closed bars whose upper wicks reject a causal EMA."""

    if ema_period <= 0:
        raise ValueError("ema_period must be positive")
    if lookback_bars < 0:
        raise ValueError("lookback_bars must be non-negative")
    if len(data) < ema_period:
        return ()
    ema = exponential_moving_average(
        data,
        ema_period,
        initial_value=initial_ema,
    )
    start = max(ema_period - 1, len(data) - lookback_bars - 1)
    return tuple(
        index
        for index in range(start, len(data))
        if data[index].high > ema[index] > max(data[index].open, data[index].close)
    )
