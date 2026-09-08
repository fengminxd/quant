"""Timeframe-specific retained history for notification scanning."""

from __future__ import annotations

from data.binance_futures import BinanceFuturesClient
from data.candle_cache import CandleCache
from data.candles import Candle
from data.market_config import SymbolConfig
from notifications.config import HISTORY_BARS, notification_window_is_ready


class NotificationWindowPolicy:
    """Keep short levels fixed while allowing extended unpromoted 4h history."""

    def __init__(self, four_hour_history_bars: int) -> None:
        if four_hour_history_bars < HISTORY_BARS:
            raise ValueError("four_hour_history_bars must be at least 201")
        self.four_hour_history_bars = four_hour_history_bars

    def history_bars(self, timeframe: str) -> int:
        """Return the retained context for one timeframe."""

        return self.four_hour_history_bars if timeframe == "4h" else HISTORY_BARS

    @staticmethod
    def ready(timeframe: str, candle_count: int) -> bool:
        """Return whether a continuous cache may enter pattern scanning."""

        return notification_window_is_ready(timeframe, candle_count)

    def update_cache(self, cache: CandleCache, candle: Candle) -> None:
        """Update one close and enforce its timeframe-specific retention limit."""

        cache.update(candle)
        limit = self.history_bars(candle.timeframe)
        candles = cache.get(candle.symbol, candle.timeframe)
        if len(candles) > limit:
            cache.replace(candle.symbol, candle.timeframe, candles[-limit:])

    async def recent_completed(
        self,
        exchange: BinanceFuturesClient,
        symbol: SymbolConfig,
        timeframe: str,
    ) -> list[Candle]:
        """Fetch the retained number of latest completed candles."""

        now = exchange.current_time_ms()
        history_bars = self.history_bars(timeframe)
        candles = await exchange.fetch_klines(
            symbol,
            timeframe,
            limit=history_bars + 1,
        )
        completed = [
            candle
            for candle in candles
            if candle.is_closed and candle.close_time < now
        ]
        return completed[-history_bars:]
