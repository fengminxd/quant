"""Crypto-only 15m scanning, scheduling and durable delivery regression tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, call

import pytest

from data.market_config import MarketDataConfig, SymbolConfig
from notifications.config import HISTORY_BARS, NotificationConfig, TelegramConfig
from notifications.event_store import NotificationEventStore
from notifications.policy import notification_timeframe_enabled
from notifications.scanner import NotificationPatternScanner
from notifications.service import RealtimeNotificationService
from tests.test_inverse_head_shoulders import pattern_bars
from tests.test_notification_reliability import FakeExchange, RecordingScanner, candles
from tests.test_notifications import notification_window


TRADEFI = (
    "XAU", "XAG", "CL", "SPCX", "MU", "SNDK", "SKHYNIX", "NVDA",
    "DRAM", "SOXL", "KORU", "MSTR",
)


@pytest.mark.parametrize("symbol", TRADEFI)
def test_tradefi_has_only_hourly_notification_levels(symbol: str) -> None:
    assert not notification_timeframe_enabled(symbol, "15m")
    assert not notification_timeframe_enabled(f"{symbol.lower()}usdt", "15m")
    assert notification_timeframe_enabled(symbol, "1h")
    assert notification_timeframe_enabled(symbol, "4h")
    assert not notification_timeframe_enabled(symbol, "1d")


@pytest.mark.parametrize("symbol", ["BTC", "ETH", "HYPE", "ONDO", *TRADEFI])
def test_scanner_accepts_crypto_but_blocks_tradefi_at_fifteen_minutes(symbol) -> None:
    bars = notification_window(pattern_bars(timeframe="15m"))
    matches = NotificationPatternScanner().scan(symbol, "15m", bars)
    if symbol in TRADEFI:
        assert matches == []
    else:
        assert any(match.pattern.pattern_id == "PATTERN_007" for match in matches)


def make_service(tmp_path, symbols) -> RealtimeNotificationService:
    """Construct an offline service with recorded exchange and Telegram calls."""
    return RealtimeNotificationService(
        NotificationConfig(TelegramConfig("token", "chat")),
        MarketDataConfig(symbols, ("15m", "1h", "4h"), HISTORY_BARS),
        exchange=FakeExchange([], 0),
        scanner=RecordingScanner(),
        telegram=AsyncMock(),
        event_store=NotificationEventStore(tmp_path / "state.sqlite3"),
    )


def test_mixed_streams_skip_tradefi_warmup_reconcile_and_health(tmp_path) -> None:
    crypto = SymbolConfig("BTC", "BTCUSDT")
    tradefi = SymbolConfig("MSTR", "MSTRUSDT")
    service = make_service(tmp_path, (crypto, tradefi))
    service.reconciler.warm = AsyncMock()
    asyncio.run(service.bootstrap())
    expected = [
        (crypto, "15m"), (crypto, "1h"), (crypto, "4h"),
        (tradefi, "1h"), (tradefi, "4h"),
    ]
    assert service.reconciler.warm.await_args_list == [
        call(symbol, timeframe, scan_latest=False) for symbol, timeframe in expected
    ]
    assert set(service.reconciler.locks) == {(s.name, t) for s, t in expected}
    assert {status.key for status in service.reconciler.statuses((crypto, tradefi), 0)} == {
        (s.name, t) for s, t in expected
    }
    service.reconciler.reconcile = AsyncMock()
    service._emit_health = AsyncMock()
    asyncio.run(service.reconcile_all(timeframes=("15m",)))
    service.reconciler.reconcile.assert_awaited_once_with(crypto, "15m", force_latest=False, boundary_ms=None)
    service.event_store.close()


def test_tradefi_only_service_keeps_hourly_schedule(tmp_path) -> None:
    service = make_service(tmp_path, (SymbolConfig("XAU", "XAUUSDT"),))
    assert service.notification_timeframes == ("1h", "4h")
    assert service.scan_interval_ms == 3_600_000
    service.event_store.close()


def test_reconciler_rejects_direct_tradefi_fifteen_minute_input(tmp_path) -> None:
    symbol = SymbolConfig("MSTR", "MSTRUSDT")
    service = make_service(tmp_path, (SymbolConfig("BTC", "BTCUSDT"), symbol))
    item = service.reconciler
    item.register((symbol,))
    asyncio.run(item.warm(symbol, "15m", scan_latest=True))
    asyncio.run(item.reconcile(symbol, "15m", force_latest=True))
    asyncio.run(item.process(replace(candles("15m", 1)[0], symbol=symbol.name)))
    assert service.exchange.fetch_calls == []
    assert service.scanner.calls == []
    assert item.cache.get(symbol.name, "15m") == []
    service.event_store.close()


def test_current_batch_delivery_filters_tradefi_15m(tmp_path) -> None:
    service = make_service(tmp_path, (SymbolConfig("BTC", "BTCUSDT"),))
    bars = notification_window(pattern_bars(timeframe="15m"))
    match = next(
        item for item in NotificationPatternScanner().scan("BTC", "15m", bars)
        if item.pattern.pattern_id == "PATTERN_007"
    )
    for symbol, timeframe in (("BTC", "15m"), ("MSTR", "15m"), ("MSTR", "1h")):
        service.event_store.enqueue(
            replace(match, symbol=symbol, timeframe=timeframe),
            filename="pattern.png", caption=f"{symbol} {timeframe}", image=b"png",
        )
    asyncio.run(service._deliver_pending(deadline_ms=10_000))
    assert {item.args[1] for item in service.telegram.send_photo.await_args_list} == {
        "BTC 15m", "MSTR 1h",
    }
    assert [(item.symbol, item.timeframe) for item in service.event_store.pending()] == [
        ("MSTR", "15m"),
    ]
    service.event_store.close()
