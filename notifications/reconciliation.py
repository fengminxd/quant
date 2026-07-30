"""Closed-candle continuity, gap recovery, and notification queueing."""

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


LOGGER = logging.getLogger(__name__)


class CandleReconciler:
    """Maintain exact 201-candle windows and replay every repaired close."""

    def __init__(
        self,
        exchange: BinanceFuturesClient,
        scanner: NotificationPatternScanner,
        event_store: NotificationEventStore,
        chart_renderer: Callable[..., bytes],
        *,
        max_restart_replay_bars: int = 1_000,
    ) -> None:
        self.exchange = exchange
        self.scanner = scanner
        self.event_store = event_store
        self.chart_renderer = chart_renderer
        self.max_restart_replay_bars = max_restart_replay_bars
        self.cache = CandleCache(maxlen=HISTORY_BARS)
        self.symbols: dict[str, SymbolConfig] = {}
        self.locks: dict[tuple[str, str], asyncio.Lock] = {}

    def register(self, symbols: Sequence[SymbolConfig]) -> None:
        """Initialize symbol lookup and one mutation lock per stream."""
        self.symbols = {symbol.name: symbol for symbol in symbols}
        self.locks = {
            (symbol.name, timeframe): asyncio.Lock()
            for symbol in symbols
            for timeframe in NOTIFICATION_TIMEFRAMES
        }

    async def warm(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        *,
        scan_latest: bool,
    ) -> None:
        """Replace one cache with the latest continuous REST window."""
        async with self.locks[(symbol.name, timeframe)]:
            if await self._restore_and_replay_locked(symbol, timeframe):
                return
            await self._reload_locked(symbol, timeframe, scan_latest=scan_latest)

    async def process(self, candle: Candle) -> None:
        """Ingest a stream close after repairing any preceding gap."""

        if not candle.is_closed or candle.timeframe not in NOTIFICATION_TIMEFRAMES:
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
    ) -> None:
        """Repair state, scanning new bars or forcibly rescanning the latest."""

        async with self.locks[(symbol.name, timeframe)]:
            candles = self.cache.get(symbol.name, timeframe)
            status = stream_health(
                symbol.name,
                timeframe,
                candles,
                self.exchange.current_time_ms(),
            )
            cursor = self.event_store.last_scanned_open_time(
                symbol.name,
                timeframe,
            )
            if cursor is not None and cursor < status.expected_open_time:
                await self._restore_and_replay_locked(symbol, timeframe)
                return
            if len(candles) != HISTORY_BARS or not status.continuous:
                restored = await self._restore_and_replay_locked(symbol, timeframe)
                if not restored:
                    await self._reload_locked(symbol, timeframe, scan_latest=True)
            elif status.lag_bars:
                await self._backfill_locked(
                    symbol,
                    timeframe,
                    status.expected_open_time,
                )
            elif cursor is None or force_latest:
                await self._scan_if_ready(symbol.name, timeframe)

    def statuses(
        self,
        symbols: Sequence[SymbolConfig],
        now_ms: int,
    ) -> list[StreamHealth]:
        return [
            stream_health(
                symbol.name,
                timeframe,
                self.cache.get(symbol.name, timeframe),
                now_ms,
            )
            for symbol in symbols
            for timeframe in NOTIFICATION_TIMEFRAMES
        ]

    async def _ingest_locked(
        self,
        symbol: SymbolConfig,
        candle: Candle,
    ) -> None:
        timeframe = candle.timeframe
        cached = self.cache.get(symbol.name, timeframe)
        if not cached:
            restored = await self._restore_and_replay_locked(symbol, timeframe)
            if not restored:
                await self._reload_locked(symbol, timeframe, scan_latest=False)
            cached = self.cache.get(symbol.name, timeframe)
        if cached and candle.open_time <= cached[-1].open_time:
            self.cache.update(candle)
            return
        interval = timeframe_to_milliseconds(timeframe)
        if cached and candle.open_time - cached[-1].open_time > interval:
            await self._backfill_locked(symbol, timeframe, candle.open_time)
        cached = self.cache.get(symbol.name, timeframe)
        if not cached or candle.open_time > cached[-1].open_time:
            self.cache.update(candle)
            await self._scan_if_ready(symbol.name, timeframe)
        if not candles_are_continuous(
            self.cache.get(symbol.name, timeframe),
            timeframe,
        ):
            await self._reload_locked(symbol, timeframe, scan_latest=True)

    async def _backfill_locked(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        target_open_time: int,
    ) -> None:
        cached = self.cache.get(symbol.name, timeframe)
        if not cached:
            await self._reload_locked(symbol, timeframe, scan_latest=True)
            return
        interval = timeframe_to_milliseconds(timeframe)
        start = cached[-1].open_time + interval
        if start > target_open_time:
            return
        count = (target_open_time - start) // interval + 1
        now = self.exchange.current_time_ms()
        fetched = await self.exchange.fetch_klines(
            symbol,
            timeframe,
            limit=count,
            start_time=start,
            end_time=target_open_time + interval - 1,
        )
        for candle in sorted(fetched, key=lambda item: item.open_time):
            if (
                candle.is_closed
                and candle.close_time < now
                and start <= candle.open_time <= target_open_time
            ):
                self.cache.update(candle)
                await self._scan_if_ready(symbol.name, timeframe)

    async def _reload_locked(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        *,
        scan_latest: bool,
    ) -> None:
        candles = await self._recent_completed(symbol, timeframe)
        self.cache.replace(symbol.name, timeframe, candles)
        if scan_latest:
            await self._scan_if_ready(symbol.name, timeframe)

    async def _restore_and_replay_locked(
        self,
        symbol: SymbolConfig,
        timeframe: str,
    ) -> bool:
        cursor = self.event_store.last_scanned_open_time(symbol.name, timeframe)
        if cursor is None:
            return False
        interval = timeframe_to_milliseconds(timeframe)
        now = self.exchange.current_time_ms()
        expected = (now // interval - 1) * interval
        if cursor >= expected:
            await self._reload_locked(symbol, timeframe, scan_latest=False)
            return True
        missing = (expected - cursor) // interval
        replay_count = min(missing, self.max_restart_replay_bars)
        first_replay = expected - (replay_count - 1) * interval
        if replay_count < missing:
            LOGGER.warning(
                "restart replay capped for %s %s: missing=%s replaying=%s",
                symbol.name,
                timeframe,
                missing,
                replay_count,
            )
        start = max(0, first_replay - (HISTORY_BARS - 1) * interval)
        count = (expected - start) // interval + 1
        fetched = await self.exchange.fetch_klines(
            symbol,
            timeframe,
            limit=count,
            start_time=start,
            end_time=expected + interval - 1,
        )
        completed = [
            candle
            for candle in sorted(fetched, key=lambda item: item.open_time)
            if candle.is_closed and candle.close_time < now
        ]
        if (
            not completed
            or completed[-1].open_time != expected
            or not candles_are_continuous(completed, timeframe)
        ):
            raise RuntimeError(
                f"restart history is incomplete for {symbol.name} {timeframe}"
            )
        prefix = [candle for candle in completed if candle.open_time < first_replay]
        self.cache.replace(symbol.name, timeframe, prefix[-(HISTORY_BARS - 1) :])
        for candle in completed:
            if candle.open_time >= first_replay:
                self.cache.update(candle)
                await self._scan_if_ready(symbol.name, timeframe)
        return True

    async def _recent_completed(
        self,
        symbol: SymbolConfig,
        timeframe: str,
    ) -> list[Candle]:
        now = self.exchange.current_time_ms()
        candles = await self.exchange.fetch_klines(
            symbol,
            timeframe,
            limit=HISTORY_BARS + 1,
        )
        completed = [
            candle
            for candle in candles
            if candle.is_closed and candle.close_time < now
        ]
        return completed[-HISTORY_BARS:]

    async def _scan_if_ready(self, symbol: str, timeframe: str) -> None:
        candles = self.cache.get(symbol, timeframe)
        if len(candles) != HISTORY_BARS:
            return
        if not candles_are_continuous(candles, timeframe):
            LOGGER.error("refusing non-continuous scan for %s %s", symbol, timeframe)
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
