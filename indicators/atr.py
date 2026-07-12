"""Average true range without look-ahead bias."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from data.validation import validate_bars


def true_ranges(data: Sequence[Bar]) -> list[float]:
    """Return historical true range values."""

    validate_bars(data)
    ranges: list[float] = []
    previous_close: float | None = None
    for bar in data:
        if previous_close is None:
            ranges.append(bar.high - bar.low)
        else:
            ranges.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )
            )
        previous_close = bar.close
    return ranges


def average_true_range(data: Sequence[Bar], period: int = 14) -> list[float]:
    """Compute rolling ATR with values available at each bar close."""

    if period <= 0:
        raise ValueError("period must be positive")
    ranges = true_ranges(data)
    atr_values: list[float] = []
    window: list[float] = []
    for value in ranges:
        window.append(value)
        if len(window) > period:
            window.pop(0)
        atr_values.append(sum(window) / len(window))
    return atr_values
