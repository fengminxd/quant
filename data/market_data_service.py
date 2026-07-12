"""Market data bootstrap and streaming orchestration."""

from __future__ import annotations

import logging

from data.binance_futures import BinanceFuturesClient
from data.candle_cache import CandleCache
from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import MarketDataConfig, SymbolConfig
from data.supabase_store import SupabaseCandleStore

LOGGER = logging.getLogger(__name__)


class MarketDataService:
    """Synchronize Binance futures candles into Supabase and memory."""

    def __init__(
        self,
        config: MarketDataConfig,
        exchange: BinanceFuturesClient,
        store: SupabaseCandleStore,
        cache: CandleCache | None = None,
    ) -> None:
        self.config = config
        self.exchange = exchange
        self.store = store
        self.cache = cache or CandleCache(maxlen=config.history_limit)
        self._active_symbols: tuple[SymbolConfig, ...] | None = None

    async def bootstrap_history(self) -> None:
        """Backfill configured symbols/timeframes and warm the memory cache."""

        for symbol in await self._get_active_symbols():
            for timeframe in self.config.timeframes:
                try:
                    candles = await self._sync_symbol_timeframe(symbol, timeframe)
                    self.cache.replace(symbol.name, timeframe, candles[-self.config.history_limit :])
                except Exception:
                    LOGGER.exception("failed to sync %s %s", symbol.exchange_symbol, timeframe)

    async def run_forever(self) -> None:
        """Bootstrap history, then stream live kline updates indefinitely."""

        await self.bootstrap_history()
        async for candle in self.exchange.stream_klines(
            await self._get_active_symbols(),
            self.config.timeframes,
        ):
            await self.store.upsert_candles([candle])
            self.cache.update(candle)

    async def _get_active_symbols(self) -> tuple[SymbolConfig, ...]:
        """Return enabled symbols validated against Binance USDT perpetual markets."""

        if self._active_symbols is None:
            self._active_symbols = await self.exchange.filter_usdt_perpetual_symbols(
                self.config.enabled_symbols
            )
        return self._active_symbols

    async def _sync_symbol_timeframe(
        self,
        symbol: SymbolConfig,
        timeframe: str,
    ) -> list[Candle]:
        latest_open_time = await self.store.latest_open_time(symbol.name, timeframe)
        interval_ms = timeframe_to_milliseconds(timeframe)
        if latest_open_time is None:
            fetched = await self.exchange.fetch_klines(
                symbol=symbol,
                timeframe=timeframe,
                limit=self.config.history_limit,
            )
            await self.store.upsert_candles(fetched)
            LOGGER.info("stored %s candles for %s %s", len(fetched), symbol.name, timeframe)
            return fetched

        now_ms = self.exchange.current_time_ms()
        start_time = latest_open_time + interval_ms
        missing_count = max(0, ((now_ms - start_time) // interval_ms) + 1)
        if missing_count > 0:
            fetched = await self.exchange.fetch_klines(
                symbol=symbol,
                timeframe=timeframe,
                limit=int(missing_count),
                start_time=start_time,
                end_time=now_ms,
            )
            continuous = self._filter_continuous(fetched, start_time, interval_ms)
            await self.store.upsert_candles(continuous)
            LOGGER.info("backfilled %s candles for %s %s", len(continuous), symbol.name, timeframe)

        return await self.store.recent_candles(symbol.name, timeframe, self.config.history_limit)

    @staticmethod
    def _filter_continuous(
        candles: list[Candle],
        expected_start: int,
        interval_ms: int,
    ) -> list[Candle]:
        """Keep only the continuous sequence from the expected start time."""

        accepted: list[Candle] = []
        expected = expected_start
        for candle in sorted(candles, key=lambda item: item.open_time):
            if candle.open_time < expected:
                continue
            if candle.open_time != expected:
                LOGGER.warning("missing candle at %s before %s", expected, candle.open_time)
                break
            accepted.append(candle)
            expected += interval_ms
        return accepted
