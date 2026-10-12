"""Interval-aligned scheduling policy for notification scans."""

from __future__ import annotations

from collections.abc import Sequence

from data.candles import timeframe_to_milliseconds
from notifications.config import NOTIFICATION_TIMEFRAMES


HOUR_MS = 3_600_000


def next_hourly_scan_ms(now_ms: int, delay_seconds: float) -> int:
    """Return the next whole-hour slot plus exchange-settlement delay."""

    return next_scan_ms(now_ms, delay_seconds, HOUR_MS)


def next_scan_ms(now_ms: int, delay_seconds: float, interval_ms: int) -> int:
    """Return the next interval boundary plus exchange-settlement delay."""

    if interval_ms <= 0:
        raise ValueError("interval_ms must be positive")
    delay_ms = int(delay_seconds * 1_000)
    adjusted = now_ms - delay_ms
    boundary = ((adjusted + interval_ms - 1) // interval_ms) * interval_ms
    return boundary + delay_ms


def scheduled_timeframes(
    boundary_ms: int,
    configured: Sequence[str],
) -> tuple[str, ...]:
    """Select only timeframes whose candles close at this scheduled boundary."""

    return tuple(
        level for level in configured
        if level in NOTIFICATION_TIMEFRAMES
        and boundary_ms % timeframe_to_milliseconds(level) == 0
    )
