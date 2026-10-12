from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import SymbolConfig
from notifications.config import HISTORY_BARS
from notifications.event_store import NotificationEventStore
from notifications.health import candles_are_continuous, stream_health
from notifications.reconciliation import CandleReconciler


SYMBOL = SymbolConfig("TEST", "TESTUSDT")


def candles(timeframe: str, count: int) -> list[Candle]:
    interval = timeframe_to_milliseconds(timeframe)
    return [
        Candle(
            symbol=SYMBOL.name,
            exchange_symbol=SYMBOL.exchange_symbol,
            timeframe=timeframe,
            open_time=index * interval,
            close_time=(index + 1) * interval - 1,
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1_000.0,
        )
        for index in range(count)
    ]


class FakeExchange:
    def __init__(self, stored: list[Candle], now_ms: int) -> None:
        self.stored = stored
        self.now_ms = now_ms
        self.discovery_failures = 0
        self.fetch_failures = 0
        self.fetch_calls: list[tuple[str, int | None, int | None]] = []

    def current_time_ms(self) -> int:
        return self.now_ms

    async def filter_usdt_perpetual_symbols(self, symbols):
        if self.discovery_failures:
            self.discovery_failures -= 1
            raise RuntimeError("exchange info unavailable")
        return symbols

    async def fetch_klines(
        self,
        symbol,
        timeframe,
        limit,
        start_time=None,
        end_time=None,
    ):
        if self.fetch_failures:
            self.fetch_failures -= 1
            raise RuntimeError("REST unavailable")
        self.fetch_calls.append((timeframe, start_time, end_time))
        selected = [
            candle
            for candle in self.stored
            if candle.timeframe == timeframe
            and candle.open_time <= self.now_ms
            and (start_time is None or candle.open_time >= start_time)
            and (end_time is None or candle.open_time <= end_time)
        ]
        return selected[-limit:] if start_time is None else selected[:limit]


class RecordingScanner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def scan(self, symbol, timeframe, bars):
        self.calls.append((timeframe, bars[-1].timestamp))
        return []


def reconciler(tmp_path, exchange: FakeExchange, scanner: RecordingScanner):
    store = NotificationEventStore(tmp_path / "state.sqlite3")
    item = CandleReconciler(exchange, scanner, store, lambda *args: b"png")
    item.register((SYMBOL,))
    return item, store


def test_continuity_and_lag_require_exact_closed_intervals() -> None:
    items = candles("1h", HISTORY_BARS)
    interval = timeframe_to_milliseconds("1h")

    assert candles_are_continuous(items, "1h")
    assert stream_health("TEST", "1h", items, HISTORY_BARS * interval + 1).healthy
    assert not candles_are_continuous([*items[:100], *items[101:]], "1h")
    assert not candles_are_continuous(
        [*items[:-1], replace(items[-1], is_closed=False)],
        "1h",
    )


def test_warmup_does_not_scan_and_same_4h_close_is_not_rescanned(tmp_path) -> None:
    interval = timeframe_to_milliseconds("4h")
    stored = candles("4h", HISTORY_BARS)
    exchange = FakeExchange(stored, HISTORY_BARS * interval + 1)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)

    asyncio.run(item.warm(SYMBOL, "4h", scan_latest=False))
    assert scanner.calls == []
    asyncio.run(item.reconcile(SYMBOL, "4h"))
    asyncio.run(item.reconcile(SYMBOL, "4h"))

    assert scanner.calls == [("4h", stored[-1].open_time)]
    asyncio.run(item.reconcile(SYMBOL, "4h", force_latest=True))
    assert scanner.calls == [
        ("4h", stored[-1].open_time),
        ("4h", stored[-1].open_time),
    ]
    store.close()


def test_warmup_then_scheduled_reconcile_skips_restart_history(
    tmp_path,
) -> None:
    interval = timeframe_to_milliseconds("1h")
    stored = candles("1h", HISTORY_BARS + 2)
    exchange = FakeExchange(stored, len(stored) * interval + 1)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)
    store.mark_scanned("TEST", "1h", stored[HISTORY_BARS - 1].open_time)

    asyncio.run(item.warm(SYMBOL, "1h", scan_latest=False))
    assert scanner.calls == []

    asyncio.run(item.reconcile(SYMBOL, "1h"))
    assert scanner.calls == [
        ("1h", stored[HISTORY_BARS + 1].open_time),
    ]
    store.close()


def test_stream_gap_repairs_context_but_scans_only_latest_close(tmp_path) -> None:
    interval = timeframe_to_milliseconds("1h")
    stored = candles("1h", HISTORY_BARS + 2)
    exchange = FakeExchange(stored, (HISTORY_BARS + 2) * interval + 1)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)
    item.cache.replace("TEST", "1h", stored[:HISTORY_BARS])

    asyncio.run(item.process(stored[-1]))

    cached = item.cache.get("TEST", "1h")
    assert candles_are_continuous(cached, "1h")
    assert cached[-1].open_time == stored[-1].open_time
    assert scanner.calls == [
        ("1h", stored[-1].open_time),
    ]
    assert exchange.fetch_calls[-1][1] is None
    store.close()


def test_failed_warmup_is_retried_by_reconciliation(tmp_path) -> None:
    interval = timeframe_to_milliseconds("1h")
    stored = candles("1h", HISTORY_BARS + 1)
    exchange = FakeExchange(stored, HISTORY_BARS * interval + 1)
    exchange.fetch_failures = 1
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)

    with pytest.raises(RuntimeError, match="REST unavailable"):
        asyncio.run(item.warm(SYMBOL, "1h", scan_latest=True))
    asyncio.run(item.reconcile(SYMBOL, "1h"))

    assert len(item.cache.get("TEST", "1h")) == HISTORY_BARS
    assert scanner.calls == [("1h", stored[HISTORY_BARS - 1].open_time)]
    store.close()


def test_restart_skips_closes_after_durable_scan_cursor(tmp_path) -> None:
    interval = timeframe_to_milliseconds("1h")
    stored = candles("1h", HISTORY_BARS + 5)
    exchange = FakeExchange(stored, len(stored) * interval + 1)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)
    cursor = stored[HISTORY_BARS - 1].open_time
    store.mark_scanned("TEST", "1h", cursor)
    exchange.fetch_failures = 1

    with pytest.raises(RuntimeError, match="REST unavailable"):
        asyncio.run(item.warm(SYMBOL, "1h", scan_latest=True))
    asyncio.run(item.reconcile(SYMBOL, "1h"))

    expected = [("1h", stored[-1].open_time)]
    assert scanner.calls == expected
    assert store.last_scanned_open_time("TEST", "1h") == stored[-1].open_time
    assert len(item.cache.get("TEST", "1h")) == HISTORY_BARS
    assert candles_are_continuous(item.cache.get("TEST", "1h"), "1h")
    store.close()


@pytest.mark.parametrize(
    ("timeframe", "future_bars", "skip_every"),
    [("1h", 72, 11), ("4h", 18, 5)],
)
def test_accelerated_three_day_soak_keeps_exact_continuous_cache(
    tmp_path,
    timeframe: str,
    future_bars: int,
    skip_every: int,
) -> None:
    interval = timeframe_to_milliseconds(timeframe)
    stored = candles(timeframe, HISTORY_BARS + future_bars)
    exchange = FakeExchange(stored, len(stored) * interval + 1)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)
    item.cache.replace("TEST", timeframe, stored[:HISTORY_BARS])

    for offset, candle in enumerate(stored[HISTORY_BARS:], start=1):
        exchange.now_ms = candle.close_time + 2
        if offset % skip_every:
            asyncio.run(item.process(candle))

    cached = item.cache.get("TEST", timeframe)
    assert len(cached) == HISTORY_BARS
    assert candles_are_continuous(cached, timeframe)
    assert len(scanner.calls) == future_bars - future_bars // skip_every
    assert cached[-1].open_time == stored[-1].open_time
    assert store.pending_count() == 0
    store.close()


def test_four_hour_cache_retains_more_than_201_without_promotion(tmp_path) -> None:
    retained = HISTORY_BARS + 49
    interval = timeframe_to_milliseconds("4h")
    stored = candles("4h", retained)
    exchange = FakeExchange(stored, retained * interval + 1)
    scanner = RecordingScanner()
    store = NotificationEventStore(tmp_path / "extended-4h.sqlite3")
    item = CandleReconciler(
        exchange,  # type: ignore[arg-type]
        scanner,  # type: ignore[arg-type]
        store,
        lambda *args: b"png",
        four_hour_history_bars=retained,
        timeframes=("4h",),
    )
    item.register((SYMBOL,))

    asyncio.run(item.warm(SYMBOL, "4h", scan_latest=True))

    assert len(item.cache.get("TEST", "4h")) == retained
    assert scanner.calls == [("4h", stored[-1].open_time)]
    store.close()
