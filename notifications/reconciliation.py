"""Closed-candle context recovery without historical alert replay."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from data.binance_futures import BinanceFuturesClient
from data.candle_cache import CandleCache
from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import SymbolConfig
from notifications.config import HISTORY_BARS, NOTIFICATION_TIMEFRAMES
from notifications.event_store import NotificationEventStore
from notifications.formatter import telegram_caption
from notifications.health import (
    StreamHealth,
    candles_are_continuous,
    stream_health,
)
from notifications.scanner import NotificationPatternScanner
from notifications.policy import notification_timeframe_enabled
from notifications.window_policy import NotificationWindowPolicy


LOGGER = logging.getLogger(__name__)


class CandleReconciler:
    """Repair retained context and scan only the current closed candle."""

    def __init__(
        self,
        exchange: BinanceFuturesClient,
        scanner: NotificationPatternScanner,
        event_store: NotificationEventStore,
        chart_renderer: Callable[..., bytes],
        *,
        four_hour_history_bars: int = HISTORY_BARS,
        timeframes: Sequence[str] = NOTIFICATION_TIMEFRAMES,
    ) -> None:
        if not timeframes or any(
            value not in NOTIFICATION_TIMEFRAMES for value in timeframes
        ):
            raise ValueError("timeframes must be supported notification levels")
        self.exchange = exchange
        self.scanner = scanner
        self.event_store = event_store
        self.chart_renderer = chart_renderer
        self.window_policy = NotificationWindowPolicy(four_hour_history_bars)
        self.timeframes = tuple(timeframes)
        self.cache = CandleCache(maxlen=four_hour_history_bars)
        self.symbols: dict[str, SymbolConfig] = {}
        self.locks: dict[tuple[str, str], asyncio.Lock] = {}

    def register(self, symbols: Sequence[SymbolConfig]) -> None:
        """Initialize symbol lookup and one mutation lock per stream."""
        self.symbols = {symbol.name: symbol for symbol in symbols}
        self.locks = {
            (symbol.name, timeframe): asyncio.Lock()
            for symbol in symbols
            for timeframe in self.timeframes
            if notification_timeframe_enabled(symbol.name, timeframe)
        }

    async def warm(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        *,
        scan_latest: bool,
    ) -> None:
        """Replace one cache with the latest continuous REST window."""
        if (symbol.name, timeframe) not in self.locks:
            return
        async with self.locks[(symbol.name, timeframe)]:
            await self._reload_locked(symbol, timeframe, scan_latest=scan_latest)

    async def process(self, candle: Candle) -> None:
        """Ingest a stream close after repairing any preceding gap."""

        if not candle.is_closed or (candle.symbol, candle.timeframe) not in self.locks:
            return
        symbol = self.symbols.get(candle.symbol)
        if symbol is None:
            return
        async with self.locks[(candle.symbol, candle.timeframe)]:
            await self._ingest_locked(symbol, candle)

    async def reconcile(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        *,
        force_latest: bool = False,
        boundary_ms: int | None = None,
    ) -> None:
        """Refresh context, then scan only the candle closing at this boundary."""

        if (symbol.name, timeframe) not in self.locks:
            return
        interval = timeframe_to_milliseconds(timeframe)
        now = self.exchange.current_time_ms()
        boundary = now // interval * interval if boundary_ms is None else boundary_ms
        if boundary % interval or not boundary <= now < boundary + interval:
            return
        async with self.locks[(symbol.name, timeframe)]:
            candles = self.cache.get(symbol.name, timeframe)
            status = stream_health(symbol.name, timeframe, candles, now)
            if not status.healthy:
                await self._reload_locked(symbol, timeframe, scan_latest=False)
            cursor = self.event_store.last_scanned_open_time(symbol.name, timeframe)
            expected = boundary - interval
            if force_latest or cursor is None or cursor < expected:
                await self._scan_if_ready(
                    symbol.name, timeframe, expected_open_time=expected,
                )

    def statuses(
        self,
        symbols: Sequence[SymbolConfig],
        now_ms: int,
    ) -> list[StreamHealth]:
        return [
            stream_health(
                symbol.name, timeframe, self.cache.get(symbol.name, timeframe), now_ms,
            )
            for symbol in symbols
            for timeframe in self.timeframes
            if notification_timeframe_enabled(symbol.name, timeframe)
        ]

    async def _ingest_locked(
        self,
        symbol: SymbolConfig,
        candle: Candle,
    ) -> None:
        timeframe = candle.timeframe
        cached = self.cache.get(symbol.name, timeframe)
        interval = timeframe_to_milliseconds(timeframe)
        if cached and candle.open_time <= cached[-1].open_time:
            return
        if not cached or candle.open_time - cached[-1].open_time > interval:
            await self._reload_locked(symbol, timeframe, scan_latest=False)
        else:
            self.window_policy.update_cache(self.cache, candle)
        await self._scan_if_ready(symbol.name, timeframe)

    async def _reload_locked(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        *,
        scan_latest: bool,
    ) -> None:
        candles = await self.window_policy.recent_completed(
            self.exchange, symbol, timeframe
        )
        self.cache.replace(symbol.name, timeframe, candles)
        if scan_latest:
            await self._scan_if_ready(symbol.name, timeframe)

    async def _scan_if_ready(
        self,
        symbol: str,
        timeframe: str,
        *,
        expected_open_time: int | None = None,
    ) -> None:
        """Reject stale, future, short or discontinuous scan windows."""

        candles = self.cache.get(symbol, timeframe)
        if not self.window_policy.ready(timeframe, len(candles)):
            return
        if not candles_are_continuous(candles, timeframe):
            LOGGER.error("refusing non-continuous scan for %s %s", symbol, timeframe)
            return
        interval = timeframe_to_milliseconds(timeframe)
        now = self.exchange.current_time_ms()
        latest = (now // interval - 1) * interval
        expected = latest if expected_open_time is None else expected_open_time
        if candles[-1].open_time != expected or expected != latest:
            return
        if candles[-1].close_time >= now:
            return
        bars = [candle.to_bar() for candle in candles]
        for match in self.scanner.scan(symbol, timeframe, bars):
            if self.event_store.contains(match.identity):
                continue
            image = self.chart_renderer(match, bars)
            self.event_store.enqueue(
                match,
                filename=(
                    f"{match.symbol}_{match.timeframe}_"
                    f"{match.pattern.pattern_id}_{match.detected_timestamp}.png"
                ),
                caption=telegram_caption(match, bars),
                image=image,
            )
        self.event_store.mark_scanned(symbol, timeframe, candles[-1].open_time)
