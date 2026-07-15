"""Causal exponential moving average used as market context only."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from data.validation import validate_bars


def exponential_moving_average(data: Sequence[Bar], period: int = 99) -> list[float]:
    """Return EMA values available at each corresponding bar close."""

    if period <= 0:
        raise ValueError("period must be positive")
    validate_bars(data)
    alpha = 2.0 / (period + 1.0)
    values = [data[0].close]
    for bar in data[1:]:
        values.append(alpha * bar.close + (1.0 - alpha) * values[-1])
    return values
