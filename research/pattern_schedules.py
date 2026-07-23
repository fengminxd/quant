"""Causal validation and pivot schedules for historical pattern scans."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from indicators.swing import PivotDetector


def validate_scan_bars(bars: Sequence[Bar], timeframe: str) -> None:
    """Require every historical bar to belong to the requested timeframe."""

    mismatch = next((bar for bar in bars if bar.timeframe != timeframe), None)
    if mismatch is not None:
        raise ValueError(
            f"bar timeframe {mismatch.timeframe!r} does not match {timeframe!r}"
        )


def pivot_confirmation_schedules(
    bars: Sequence[Bar],
) -> dict[str, set[int]]:
    """Precompute causal raw-pivot confirmation times by detector radius."""

    schedules = {"low_2": set(), "low_5": set(), "high_2": set(), "high_5": set()}
    if len(bars) >= 5:
        for pivot in PivotDetector(left=2, right=2).detect(bars):
            schedules[f"{pivot.kind}_2"].add(pivot.confirmed_at)
    if len(bars) >= 11:
        for pivot in PivotDetector(left=5, right=5).detect(bars):
            schedules[f"{pivot.kind}_5"].add(pivot.confirmed_at)
    return schedules
