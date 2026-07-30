"""Self-healing Binance-to-Telegram real-time Pattern service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from data.binance_futures import BinanceFuturesClient
from data.market_config import MarketDataConfig, SymbolConfig
from notifications.chart import render_notification_chart
from notifications.config import NOTIFICATION_TIMEFRAMES, NotificationConfig
from notifications.event_store import NotificationEventStore
from notifications.health import StreamHealth, health_alert_text
from notifications.reconciliation import CandleReconciler
from notifications.scanner import NotificationPatternScanner
from notifications.telegram import TelegramClient


LOGGER = logging.getLogger(__name__)
HOUR_MS = 3_600_000
UTC_PLUS_8 = timezone(timedelta(hours=8))


def next_hourly_scan_ms(now_ms: int, delay_seconds: float) -> int:
    """Return the next UTC+8 whole-hour slot plus exchange-settlement delay."""

    delay_ms = int(delay_seconds * 1_000)
    adjusted = now_ms - delay_ms
    boundary = ((adjusted + HOUR_MS - 1) // HOUR_MS) * HOUR_MS
    return boundary + delay_ms


class RealtimeNotificationService:
    """Run hourly REST reconciliation plus independent Outbox delivery."""

    def __init__(
        self,
        config: NotificationConfig,
        market: MarketDataConfig,
        *,
        exchange: BinanceFuturesClient | None = None,
        scanner: NotificationPatternScanner | None = None,
        telegram: TelegramClient | None = None,
        event_store: NotificationEventStore | None = None,
        chart_renderer: Callable[..., bytes] = render_notification_chart,
    ) -> None:
        self.config = config
        self.market = market
        self.exchange = exchange or BinanceFuturesClient()
        self.scanner = scanner or NotificationPatternScanner()
        self.telegram = telegram or TelegramClient(config.telegram)
        self.event_store = event_store or NotificationEventStore(config.state_db)
        self.reconciler = CandleReconciler(
            self.exchange,
            self.scanner,
            self.event_store,
            chart_renderer,
            max_restart_replay_bars=config.max_restart_replay_bars,
        )
        self.cache = self.reconciler.cache
        self.active_symbols: tuple[SymbolConfig, ...] = ()
        self._delivery_lock = asyncio.Lock()
        self._unhealthy: set[tuple[str, str]] = set()
        self._last_heartbeat = 0.0

    async def run_forever(self) -> None:
        """Bootstrap, then supervise hourly scans and the Telegram Outbox."""

        await self._deliver_pending()
        await self.bootstrap()
        await self.reconcile_all(force_latest=True)
        await self._deliver_pending()
        await self._emit_health(force=True)
        tasks = (
            asyncio.create_task(self._hourly_scan_loop()),
            asyncio.create_task(self._outbox_loop()),
        )
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.event_store.close()

    async def bootstrap(self) -> None:
        """Retry market discovery and warm each stream without blocking others."""

        self.active_symbols = await self._load_active_symbols()
        self.reconciler.register(self.active_symbols)
        for symbol in self.active_symbols:
            for timeframe in NOTIFICATION_TIMEFRAMES:
                try:
                    await self.reconciler.warm(
                        symbol,
                        timeframe,
                        scan_latest=False,
                    )
                except Exception:
                    LOGGER.exception(
                        "bootstrap pending retry for %s %s",
                        symbol.name,
                        timeframe,
                    )

    async def reconcile_all(self, *, force_latest: bool = False) -> None:
        """Retry failed warm-ups and repair every data stream."""

        for symbol in self.active_symbols:
            for timeframe in NOTIFICATION_TIMEFRAMES:
                try:
                    await self.reconciler.reconcile(
                        symbol,
                        timeframe,
                        force_latest=force_latest,
                    )
                except Exception:
                    LOGGER.exception(
                        "candle reconciliation failed for %s %s",
                        symbol.name,
                        timeframe,
                    )
        await self._emit_health()

    async def _hourly_scan_loop(self) -> None:
        """Sleep until each UTC+8 whole hour, then run one REST scan."""

        while True:
            now_ms = self.exchange.current_time_ms()
            target_ms = next_hourly_scan_ms(
                now_ms,
                self.config.scan_delay_seconds,
            )
            target = datetime.fromtimestamp(target_ms / 1_000, UTC_PLUS_8)
            LOGGER.info("next notification scan at %s UTC+8", target.isoformat())
            await asyncio.sleep(max(0.0, (target_ms - now_ms) / 1_000))
            await self.reconcile_all()
            await asyncio.sleep(0.05)

    async def _outbox_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.delivery_retry_interval_seconds)
            await self._deliver_pending()

    async def _load_active_symbols(self) -> tuple[SymbolConfig, ...]:
        if not self.market.enabled_symbols:
            raise ValueError("at least one enabled notification symbol is required")
        while True:
            try:
                active = await self.exchange.filter_usdt_perpetual_symbols(
                    self.market.enabled_symbols
                )
                if not active:
                    raise RuntimeError("no configured symbol is an active USDT perpetual")
                return active
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("market discovery failed; retrying")
                await asyncio.sleep(self.config.bootstrap_retry_seconds)

    async def _deliver_pending(self) -> None:
        async with self._delivery_lock:
            for item in self.event_store.pending():
                try:
                    await self.telegram.send_photo(
                        item.image,
                        item.caption,
                        filename=item.filename,
                    )
                except RuntimeError as error:
                    LOGGER.warning(
                        "Telegram remains pending for %s %s %s: %s",
                        item.symbol,
                        item.timeframe,
                        item.pattern_id,
                        error,
                    )
                    continue
                self.event_store.mark_pending_sent(item)
                LOGGER.info(
                    "sent %s %s %s",
                    item.symbol,
                    item.timeframe,
                    item.pattern_id,
                )

    async def _emit_health(self, *, force: bool = False) -> None:
        statuses = self.reconciler.statuses(
            self.active_symbols,
            self.exchange.current_time_ms(),
        )
        for status in statuses:
            alerting = (
                status.candle_count != 201
                or not status.continuous
                or status.lag_bars is None
                or status.lag_bars >= self.config.data_lag_alert_bars
            )
            if alerting and status.key not in self._unhealthy:
                self._unhealthy.add(status.key)
                await self._send_health_alert(status, recovered=False)
            elif status.healthy and status.key in self._unhealthy:
                self._unhealthy.remove(status.key)
                await self._send_health_alert(status, recovered=True)
        now = time.monotonic()
        if force or now - self._last_heartbeat >= self.config.heartbeat_interval_seconds:
            healthy = sum(status.healthy for status in statuses)
            LOGGER.info(
                "heartbeat streams=%s/%s healthy pending=%s",
                healthy,
                len(statuses),
                self.event_store.pending_count(),
            )
            self._last_heartbeat = now

    async def _send_health_alert(
        self,
        status: StreamHealth,
        *,
        recovered: bool,
    ) -> None:
        try:
            await self.telegram.send_message(
                health_alert_text(status, recovered=recovered)
            )
        except RuntimeError as error:
            LOGGER.warning(
                "Telegram health alert failed for %s %s: %s",
                status.symbol,
                status.timeframe,
                error,
            )
