"""Notification scan clock and timeframe-gating tests."""

from __future__ import annotations

import pytest

from data.candles import timeframe_to_milliseconds
from notifications.schedule import (
    HOUR_MS,
    latest_scan_boundary_ms,
    next_hourly_scan_ms,
    next_scan_ms,
    scheduled_timeframes,
)


def test_hourly_scheduler_aligns_to_boundary_plus_settlement_delay() -> None:
    delay_ms = 5_000

    assert next_hourly_scan_ms(12 * HOUR_MS + 2_000, 5) == (
        12 * HOUR_MS + delay_ms
    )
    assert next_hourly_scan_ms(12 * HOUR_MS + 6_000, 5) == (
        13 * HOUR_MS + delay_ms
    )
    assert next_hourly_scan_ms(12 * HOUR_MS + delay_ms, 5) == (
        12 * HOUR_MS + delay_ms
    )


def test_fifteen_minute_scheduler_aligns_to_each_close() -> None:
    quarter = timeframe_to_milliseconds("15m")

    assert next_scan_ms(12 * HOUR_MS + 2_000, 5, quarter) == (
        12 * HOUR_MS + 5_000
    )
    assert next_scan_ms(12 * HOUR_MS + 6_000, 5, quarter) == (
        12 * HOUR_MS + quarter + 5_000
    )


@pytest.mark.parametrize(
    ("minute", "expected"),
    [
        (0, ("15m", "1h", "4h")),
        (15, ("15m",)),
        (30, ("15m",)),
        (45, ("15m",)),
    ],
)
def test_scan_slot_only_includes_hourly_levels_on_the_hour(
    minute: int,
    expected: tuple[str, ...],
) -> None:
    boundary_ms = 12 * HOUR_MS + minute * 60_000

    assert scheduled_timeframes(
        boundary_ms,
        ("15m", "1h", "4h"),
    ) == expected


def test_latest_settled_boundary_drives_startup_timeframe_gate() -> None:
    quarter = timeframe_to_milliseconds("15m")

    assert latest_scan_boundary_ms(12 * HOUR_MS + 8_000, 5, quarter) == (
        12 * HOUR_MS
    )
    assert latest_scan_boundary_ms(
        12 * HOUR_MS + quarter + 8_000,
        5,
        quarter,
    ) == 12 * HOUR_MS + quarter
