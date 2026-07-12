from __future__ import annotations

from core.models import Bar


def make_bar(index: int, high: float, low: float, close: float | None = None) -> Bar:
    close_price = close if close is not None else (high + low) / 2.0
    return Bar(
        timestamp=index,
        open=close_price,
        high=high,
        low=low,
        close=close_price,
        volume=max(100.0, 1000.0 - index * 10.0),
    )
