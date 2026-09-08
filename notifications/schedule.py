"""Interval-aligned scheduling policy for notification scans."""

from __future__ import annotations

from collections.abc import Sequence


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
    """Return levels due at a UTC+8-aligned quarter-hour boundary.

    UTC+8 is an exact number of hours, so epoch-hour modulo yields the same
    whole-hour boundaries in UTC and UTC+8.
    """

    if boundary_ms % HOUR_MS == 0:
        return tuple(configured)
    return tuple(timeframe for timeframe in configured if timeframe == "15m")


def latest_scan_boundary_ms(
    now_ms: int,
    delay_seconds: float,
    interval_ms: int,
) -> int:
    """Return the latest settled interval boundary at or before now."""

    if interval_ms <= 0:
        raise ValueError("interval_ms must be positive")
    delay_ms = int(delay_seconds * 1_000)
    return ((now_ms - delay_ms) // interval_ms) * interval_ms
