"""Temporal de-duplication for historical Pattern scan events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from research.pattern_scan import PatternScanEvent


def select_temporally_distinct_events(
    events: Iterable[PatternScanEvent],
    nearby_hours: float = 24.0,
) -> list[PatternScanEvent]:
    """Keep the strongest same-rule structure in each nearby time bucket."""

    if nearby_hours < 0.0:
        raise ValueError("nearby_hours must be non-negative")
    grouped: dict[tuple[str, str, str], list[PatternScanEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.timeframe, event.pattern_id, event.rule)].append(event)
    selected: list[PatternScanEvent] = []
    window_ms = round(nearby_hours * 3_600_000)
    for candidates in grouped.values():
        ordered = sorted(candidates, key=lambda event: _timestamp_ms(event.detected_timestamp))
        bucket: list[PatternScanEvent] = []
        bucket_start = 0
        for event in ordered:
            timestamp = _timestamp_ms(event.detected_timestamp)
            if bucket and timestamp - bucket_start > window_ms:
                selected.append(max(bucket, key=_quality_rank))
                bucket = []
            if not bucket:
                bucket_start = timestamp
            bucket.append(event)
        if bucket:
            selected.append(max(bucket, key=_quality_rank))
    return sorted(
        selected,
        key=lambda event: (
            event.timeframe,
            _timestamp_ms(event.detected_timestamp),
            event.pattern_id,
            event.rule,
        ),
    )


def _quality_rank(event: PatternScanEvent) -> tuple[float, float, float, int, int, int]:
    span = event.last_anchor_index - event.first_anchor_index
    return (
        float(event.priority_fixed_combination),
        event.priority_combination_score,
        event.score,
        span,
        event.last_anchor_index,
        _timestamp_ms(event.detected_timestamp),
    )


def _timestamp_ms(timestamp: int | str) -> int:
    if isinstance(timestamp, int):
        return timestamp
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round(value.timestamp() * 1000)
