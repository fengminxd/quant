"""Scheduled live alerts must never recover historical deliveries."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from notifications.event_store import NotificationEventStore
from notifications.scanner import NotificationPatternScanner
from tests.test_inverse_head_shoulders import pattern_bars
from tests.test_notification_reliability import (
    SYMBOL, FakeExchange, RecordingScanner, candles, reconciler,
)
from tests.test_notification_service import make_service
from tests.test_notifications import notification_window


HOUR = 3_600_000


@pytest.fixture
def match():
    """Supply a valid pattern payload without network access."""
    return next(
        item for item in NotificationPatternScanner().scan(
            "TEST", "1h", notification_window(pattern_bars()),
        ) if item.pattern.pattern_id == "PATTERN_007"
    )


def enqueue(store, match) -> None:
    """Persist a representative pending image."""
    store.enqueue(match, filename="pattern.png", caption="live", image=b"png")


def test_startup_discards_old_queue_without_scanning_or_sending(tmp_path, match):
    service = make_service(tmp_path, FakeExchange([], 12 * HOUR + 30_000))
    enqueue(service.event_store, match)
    service.bootstrap = AsyncMock()
    service._scan_loop = AsyncMock()
    service.reconcile_all = AsyncMock()
    service.telegram = AsyncMock()

    asyncio.run(service.run_forever())

    service.bootstrap.assert_awaited_once()
    service._scan_loop.assert_awaited_once()
    service.reconcile_all.assert_not_awaited()
    service.telegram.send_photo.assert_not_awaited()
    service.telegram.send_message.assert_not_awaited()
    reopened = NotificationEventStore(tmp_path / "service.sqlite3")
    assert reopened.pending_count() == 0
    assert not reopened.contains(match.identity)
    reopened.close()


@pytest.mark.parametrize("fail", [False, True])
def test_scheduled_batch_sends_only_new_payload_and_never_retries_old_one(
    tmp_path, match, fail,
):
    exchange = FakeExchange([], 12 * HOUR + 5_000)
    telegram = AsyncMock()
    if fail:
        telegram.send_photo.side_effect = RuntimeError("offline")
    service = make_service(tmp_path, exchange, telegram=telegram)
    enqueue(service.event_store, match)
    live = replace(match, detected_timestamp=12 * HOUR)

    async def scan(**kwargs):
        assert service.event_store.pending_count() == 0
        enqueue(service.event_store, live)

    service.reconcile_all = AsyncMock(side_effect=scan)
    service._emit_health = AsyncMock()
    asyncio.run(service._run_scheduled_scan(12 * HOUR, ("1h",)))
    assert telegram.send_photo.await_count == 1
    assert service.event_store.pending_count() == 0
    assert not service.event_store.contains(match.identity)
    assert service.event_store.contains(live.identity) == (not fail)

    exchange.now_ms += HOUR
    service.reconcile_all = AsyncMock()
    asyncio.run(service._run_scheduled_scan(13 * HOUR, ("1h",)))
    assert telegram.send_photo.await_count == 1
    service.event_store.close()


def test_batch_that_finishes_after_deadline_drops_payload(tmp_path, match):
    exchange = FakeExchange([], 12 * HOUR + 5_000)
    service = make_service(tmp_path, exchange, telegram=AsyncMock())

    async def slow_scan(**kwargs):
        enqueue(service.event_store, match)
        exchange.now_ms += service.scan_interval_ms

    service.reconcile_all = AsyncMock(side_effect=slow_scan)
    asyncio.run(service._run_scheduled_scan(12 * HOUR, ("1h",)))
    service.telegram.send_photo.assert_not_awaited()
    assert service.event_store.pending_count() == 0
    service.event_store.close()


def test_in_flight_delivery_is_cancelled_at_slot_deadline(tmp_path, match):
    exchange = FakeExchange([], 12 * HOUR + 5_000)
    service = make_service(tmp_path, exchange, telegram=AsyncMock())
    cancelled = []

    async def scan(**kwargs):
        enqueue(service.event_store, match)
        exchange.now_ms += service.scan_interval_ms - 1

    async def send(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    service.reconcile_all = AsyncMock(side_effect=scan)
    service.telegram.send_photo.side_effect = send
    asyncio.run(service._run_scheduled_scan(12 * HOUR, ("1h",)))
    assert cancelled == [True]
    assert service.event_store.pending_count() == 0
    assert not service.event_store.contains(match.identity)
    service.event_store.close()


def test_delayed_scheduler_skips_missed_slot(tmp_path):
    exchange = FakeExchange([], 12 * HOUR)
    service = make_service(tmp_path, exchange)
    service._run_scheduled_scan = AsyncMock()
    sleeps = 0

    async def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            exchange.now_ms += 30_000
        else:
            raise asyncio.CancelledError

    with patch("notifications.service.asyncio.sleep", side_effect=sleep):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(service._scan_loop())
    service._run_scheduled_scan.assert_not_awaited()
    service.event_store.close()


@pytest.mark.parametrize("timeframe,boundary", [("1h", 204 * HOUR), ("4h", 805 * HOUR)])
def test_stale_data_or_non_four_hour_boundary_cannot_generate_alerts(
    tmp_path, timeframe, boundary,
):
    exchange = FakeExchange(candles(timeframe, 201), boundary + 5_000)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)
    asyncio.run(item.reconcile(SYMBOL, timeframe, boundary_ms=boundary))
    assert scanner.calls == []
    store.close()


def test_recovery_scans_only_current_close_with_full_context(tmp_path):
    stored = candles("1h", 208)
    exchange = FakeExchange(stored, 208 * HOUR + 5_000)
    scanner = RecordingScanner()
    item, store = reconciler(tmp_path, exchange, scanner)
    store.mark_scanned("TEST", "1h", 200 * HOUR)
    asyncio.run(item.reconcile(SYMBOL, "1h", boundary_ms=208 * HOUR))
    assert scanner.calls == [("1h", 207 * HOUR)]
    assert len(item.cache.get("TEST", "1h")) == 201
    store.close()
