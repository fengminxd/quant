"""Notification service orchestration and health behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import MarketDataConfig, SymbolConfig
from notifications.config import HISTORY_BARS, NotificationConfig, TelegramConfig
from notifications.event_store import NotificationEventStore
from notifications.service import RealtimeNotificationService


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


class ServiceExchange:
    def __init__(self, stored: list[Candle], now_ms: int) -> None:
        self.stored = stored
        self.now_ms = now_ms
        self.discovery_failures = 0

    def current_time_ms(self) -> int:
        return self.now_ms

    async def filter_usdt_perpetual_symbols(self, symbols):
        if self.discovery_failures:
            self.discovery_failures -= 1
            raise RuntimeError("exchange info unavailable")
        return symbols


class RecordingScanner:
    def scan(self, symbol, timeframe, bars):
        return []


class RecordingTelegram:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, text: str) -> None:
        self.messages.append(text)

    async def send_photo(self, image, caption, *, filename) -> None:
        return None


def make_service(
    tmp_path,
    exchange,
    *,
    telegram=None,
    timeframes=("15m", "1h", "4h"),
) -> RealtimeNotificationService:
    return RealtimeNotificationService(
        NotificationConfig(TelegramConfig("token", "chat")),
        MarketDataConfig((SYMBOL,), timeframes, HISTORY_BARS),
        exchange=exchange,
        scanner=RecordingScanner(),
        telegram=telegram,
        event_store=NotificationEventStore(tmp_path / "service.sqlite3"),
    )


def test_symbol_discovery_retries_transient_startup_failure(tmp_path) -> None:
    exchange = ServiceExchange([], 0)
    exchange.discovery_failures = 1
    service = RealtimeNotificationService(
        NotificationConfig(
            TelegramConfig("token", "chat"),
            bootstrap_retry_seconds=0.001,
        ),
        MarketDataConfig((SYMBOL,), ("1h", "4h"), HISTORY_BARS),
        exchange=exchange,
        event_store=NotificationEventStore(tmp_path / "discovery.sqlite3"),
    )

    assert asyncio.run(service._load_active_symbols()) == (SYMBOL,)
    service.event_store.close()


def test_service_uses_15m_schedule_and_extended_4h_window(tmp_path) -> None:
    service = RealtimeNotificationService(
        NotificationConfig(
            TelegramConfig("token", "chat"),
            four_hour_history_bars=350,
        ),
        MarketDataConfig((SYMBOL,), ("15m", "1h", "4h"), 2_000),
        exchange=ServiceExchange([], 0),
        scanner=RecordingScanner(),
        event_store=NotificationEventStore(tmp_path / "levels.sqlite3"),
    )

    assert service.notification_timeframes == ("15m", "1h", "4h")
    assert service.scan_interval_ms == timeframe_to_milliseconds("15m")
    assert service.reconciler.window_policy.history_bars("4h") == 350
    service.event_store.close()


def test_reconcile_all_only_calls_due_timeframes(tmp_path) -> None:
    service = make_service(tmp_path, ServiceExchange([], 0))
    service.active_symbols = (SYMBOL,)
    reconcile = AsyncMock()
    service.reconciler.reconcile = reconcile
    service._emit_health = AsyncMock()

    asyncio.run(service.reconcile_all(timeframes=("15m",)))

    reconcile.assert_awaited_once_with(SYMBOL, "15m", force_latest=False)
    service.event_store.close()


def test_health_alerts_emit_once_then_emit_recovery(tmp_path) -> None:
    one_hour = candles("1h", HISTORY_BARS)
    four_hour = candles("4h", HISTORY_BARS)
    now = HISTORY_BARS * timeframe_to_milliseconds("4h") + 1
    telegram = RecordingTelegram()
    service = make_service(
        tmp_path,
        ServiceExchange([*one_hour, *four_hour], now),
        telegram=telegram,
        timeframes=("1h", "4h"),
    )
    service.active_symbols = (SYMBOL,)
    service.reconciler.register((SYMBOL,))

    asyncio.run(service._emit_health(force=True))
    assert len(telegram.messages) == 2
    service.reconciler.cache.replace("TEST", "1h", one_hour)
    service.reconciler.cache.replace("TEST", "4h", four_hour)
    asyncio.run(service._emit_health())

    assert len(telegram.messages) == 3
    assert "恢复" in telegram.messages[-1]
    service.event_store.close()
