from __future__ import annotations

import asyncio
from collections.abc import Sequence

from data.candle_cache import CandleCache
from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import MarketDataConfig, SymbolConfig
from data.market_data_service import MarketDataService


def make_candle(symbol: SymbolConfig, timeframe: str, open_time: int) -> Candle:
    return Candle(
        symbol=symbol.name,
        exchange_symbol=symbol.exchange_symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=open_time + timeframe_to_milliseconds(timeframe) - 1,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=100.0,
    )


class FakeExchange:
    def __init__(
        self,
        now_ms: int,
        interval_ms: int,
        valid_symbols: tuple[str, ...] | None = None,
    ) -> None:
        self.now_ms = now_ms
        self.interval_ms = interval_ms
        self.valid_symbols = valid_symbols
        self.calls: list[dict[str, int | None]] = []

    def current_time_ms(self) -> int:
        return self.now_ms

    async def filter_usdt_perpetual_symbols(
        self,
        symbols: tuple[SymbolConfig, ...],
    ) -> tuple[SymbolConfig, ...]:
        if self.valid_symbols is None:
            return symbols
        allowed = set(self.valid_symbols)
        return tuple(symbol for symbol in symbols if symbol.exchange_symbol in allowed)

    async def fetch_klines(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        limit: int,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        self.calls.append({"limit": limit, "start_time": start_time, "end_time": end_time})
        first = start_time if start_time is not None else self.now_ms - (limit - 1) * self.interval_ms
        return [make_candle(symbol, timeframe, first + index * self.interval_ms) for index in range(limit)]


class FakeStore:
    def __init__(self, rows: Sequence[Candle] = ()) -> None:
        self.rows = {(row.symbol, row.timeframe, row.open_time): row for row in rows}

    async def latest_closed_open_time(
        self,
        symbol: str,
        timeframe: str,
        max_open_time: int,
    ) -> int | None:
        times = [
            time
            for (row_symbol, row_tf, time), row in self.rows.items()
            if row_symbol == symbol
            and row_tf == timeframe
            and row.is_closed
            and time <= max_open_time
        ]
        return max(times) if times else None

    async def recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        rows = [
            row
            for (row_symbol, row_tf, _), row in self.rows.items()
            if row_symbol == symbol and row_tf == timeframe
        ]
        return sorted(rows, key=lambda row: row.open_time)[-limit:]

    async def upsert_candles(self, candles: Sequence[Candle]) -> None:
        for candle in candles:
            self.rows[(candle.symbol, candle.timeframe, candle.open_time)] = candle


def test_bootstrap_fetches_2000_when_symbol_has_no_data() -> None:
    symbol = SymbolConfig("BTC", "BTCUSDT")
    config = MarketDataConfig((symbol,), ("15m",), 2000)
    exchange = FakeExchange(now_ms=2_000 * 900_000, interval_ms=900_000)
    store = FakeStore()
    service = MarketDataService(config, exchange, store)

    asyncio.run(service.bootstrap_history())

    assert exchange.calls[0]["limit"] == 2001
    assert len(service.cache.get("BTC", "15m")) == 2000


def test_bootstrap_backfills_from_latest_open_time() -> None:
    symbol = SymbolConfig("BTC", "BTCUSDT")
    existing = make_candle(symbol, "15m", 0)
    config = MarketDataConfig((symbol,), ("15m",), 2000)
    exchange = FakeExchange(now_ms=2 * 900_000, interval_ms=900_000)
    store = FakeStore([existing])
    service = MarketDataService(config, exchange, store)

    asyncio.run(service.bootstrap_history())

    assert exchange.calls[0]["start_time"] == 900_000
    assert len(service.cache.get("BTC", "15m")) == 2


def test_bootstrap_skips_symbols_that_are_not_usdt_perpetuals() -> None:
    btc = SymbolConfig("BTC", "BTCUSDT")
    xau = SymbolConfig("XAU", "XAUUSDT")
    config = MarketDataConfig((btc, xau), ("15m",), 2000)
    exchange = FakeExchange(
        now_ms=2_000 * 900_000,
        interval_ms=900_000,
        valid_symbols=("BTCUSDT",),
    )
    store = FakeStore()
    service = MarketDataService(config, exchange, store)

    asyncio.run(service.bootstrap_history())

    assert len(exchange.calls) == 1
    assert len(service.cache.get("BTC", "15m")) == 2000
    assert service.cache.get("XAU", "15m") == []


def test_candle_cache_keeps_latest_2000_and_replaces_live_candle() -> None:
    symbol = SymbolConfig("BTC", "BTCUSDT")
    cache = CandleCache(maxlen=2)
    cache.update(make_candle(symbol, "15m", 0))
    cache.update(make_candle(symbol, "15m", 900_000))
    cache.update(make_candle(symbol, "15m", 1_800_000))
    replacement = make_candle(symbol, "15m", 1_800_000)

    cache.update(replacement)

    rows = cache.get("BTC", "15m")
    assert [row.open_time for row in rows] == [900_000, 1_800_000]
    assert rows[-1] is replacement
