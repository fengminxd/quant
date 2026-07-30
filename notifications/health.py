"""Continuity and lag measurements for the notification service."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from data.candles import Candle, timeframe_to_milliseconds


@dataclass(frozen=True)
class StreamHealth:
    """Latest cache status for one symbol/timeframe."""

    symbol: str
    timeframe: str
    candle_count: int
    latest_open_time: int | None
    expected_open_time: int
    lag_bars: int | None
    continuous: bool

    @property
    def healthy(self) -> bool:
        return (
            self.candle_count == 201
            and self.lag_bars == 0
            and self.continuous
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.symbol, self.timeframe


def stream_health(
    symbol: str,
    timeframe: str,
    candles: Sequence[Candle],
    now_ms: int,
) -> StreamHealth:
    """Measure cache completeness, interval continuity, and exchange-time lag."""

    interval = timeframe_to_milliseconds(timeframe)
    expected = (now_ms // interval - 1) * interval
    latest = candles[-1].open_time if candles else None
    lag = None if latest is None else max(0, (expected - latest) // interval)
    return StreamHealth(
        symbol,
        timeframe,
        len(candles),
        latest,
        expected,
        lag,
        candles_are_continuous(candles, timeframe),
    )


def candles_are_continuous(
    candles: Sequence[Candle],
    timeframe: str,
) -> bool:
    """Require chronological, closed, gap-free candles for Pattern geometry."""

    if not candles or any(not candle.is_closed for candle in candles):
        return False
    interval = timeframe_to_milliseconds(timeframe)
    return all(
        current.open_time - previous.open_time == interval
        for previous, current in zip(candles, candles[1:])
    )


def health_alert_text(status: StreamHealth, *, recovered: bool) -> str:
    """Format one transition message without including any secret values."""

    state = "恢复" if recovered else "异常"
    lag = "-" if status.lag_bars is None else str(status.lag_bars)
    return "\n".join(
        (
            f"Pattern通知数据{state}",
            f"symbol: {status.symbol}",
            f"周期: {status.timeframe}",
            f"缓存K线: {status.candle_count}/201",
            f"延迟K线数: {lag}",
            f"连续性: {'正常' if status.continuous else '异常'}",
        )
    )
