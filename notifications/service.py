"""Self-healing Binance-to-Telegram real-time Pattern service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from data.binance_futures import BinanceFuturesClient
from data.candles import timeframe_to_milliseconds
from data.market_config import MarketDataConfig, SymbolConfig
from notifications.chart import render_notification_chart
from notifications.config import (
    HISTORY_BARS,
    NOTIFICATION_TIMEFRAMES,
    NotificationConfig,
    notification_window_is_ready,
)
from notifications.event_store import NotificationEventStore
from notifications.health import StreamHealth, health_alert_text
from notifications.reconciliation import CandleReconciler
from notifications.schedule import (
    latest_scan_boundary_ms,
    next_scan_ms,
    scheduled_timeframes,
)
from notifications.scanner import NotificationPatternScanner
from notifications.telegram import TelegramClient


LOGGER = logging.getLogger(__name__)
UTC_PLUS_8 = timezone(timedelta(hours=8))


class RealtimeNotificationService:
    """Run interval-aligned REST reconciliation and independent Outbox delivery."""

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
        configured = set(market.trading_timeframes)
        self.notification_timeframes = tuple(
            timeframe
            for timeframe in NOTIFICATION_TIMEFRAMES
            if timeframe in configured
        )
        if not self.notification_timeframes:
            raise ValueError("at least one notification timeframe must be configured")
        self.scan_interval_ms = min(
            timeframe_to_milliseconds(value) for value in self.notification_timeframes
        )
        self.reconciler = CandleReconciler(
            self.exchange,
            self.scanner,
            self.event_store,
            chart_renderer,
            max_restart_replay_bars=config.max_restart_replay_bars,
            four_hour_history_bars=config.four_hour_history_bars,
            timeframes=self.notification_timeframes,
        )
        self.cache = self.reconciler.cache
        self.active_symbols: tuple[SymbolConfig, ...] = ()
        self._delivery_lock = asyncio.Lock()
        self._unhealthy: set[tuple[str, str]] = set()
        self._last_heartbeat = 0.0

    async def run_forever(self) -> None:
        """Bootstrap, then supervise scheduled scans and the Telegram Outbox."""

        await self._deliver_pending()
        await self.bootstrap()
        boundary_ms = latest_scan_boundary_ms(
            self.exchange.current_time_ms(),
            self.config.scan_delay_seconds,
            self.scan_interval_ms,
        )
        await self.reconcile_all(
            force_latest=True,
            timeframes=scheduled_timeframes(
                boundary_ms,
                self.notification_timeframes,
            ),
        )
        await self._deliver_pending()
        await self._emit_health(force=True)
        tasks = (
            asyncio.create_task(self._scan_loop()),
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
            for timeframe in self.notification_timeframes:
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

    async def reconcile_all(
        self,
        *,
        force_latest: bool = False,
        timeframes: Sequence[str] | None = None,
    ) -> None:
        """Repair the requested timeframe streams for every active symbol."""

        due_timeframes = tuple(
            self.notification_timeframes if timeframes is None else timeframes
        )
        for symbol in self.active_symbols:
            for timeframe in due_timeframes:
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

    async def _scan_loop(self) -> None:
        """Reconcile at the smallest configured notification interval."""

        while True:
            now_ms = self.exchange.current_time_ms()
            target_ms = next_scan_ms(
                now_ms,
                self.config.scan_delay_seconds,
                self.scan_interval_ms,
            )
            target = datetime.fromtimestamp(target_ms / 1_000, UTC_PLUS_8)
            boundary_ms = target_ms - int(self.config.scan_delay_seconds * 1_000)
            due_timeframes = scheduled_timeframes(
                boundary_ms,
                self.notification_timeframes,
            )
            LOGGER.info(
                "next notification scan at %s UTC+8 timeframes=%s",
                target.isoformat(),
                ",".join(due_timeframes),
            )
            await asyncio.sleep(max(0.0, (target_ms - now_ms) / 1_000))
            await self.reconcile_all(timeframes=due_timeframes)
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
                not notification_window_is_ready(
                    status.timeframe, status.candle_count
                )
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
