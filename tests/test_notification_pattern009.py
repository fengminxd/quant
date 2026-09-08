from __future__ import annotations

from dataclasses import replace

import pytest

from notifications.config import (
    HISTORY_BARS,
    NOTIFICATION_TIMEFRAMES,
    notification_window_is_ready,
)
from notifications.formatter import telegram_caption
from notifications.scanner import NotificationPatternScanner
from research.pattern_lines import pattern_line_groups
from tests.test_near_4h_triangle import near_bars
from tests.test_parallel_channel import parallel_channel_bars


def channel_bars(
    timeframe: str,
    length: int,
    lower_anchors: tuple[int, ...],
    upper_anchors: tuple[int, ...],
):
    """Return an exact channel whose provisional last low is the right edge."""

    return [
        replace(bar, timeframe=timeframe)
        for bar in parallel_channel_bars(
            length=length,
            lower_anchors=lower_anchors,
            upper_anchors=upper_anchors,
        )
    ]


def test_notification_levels_include_fifteen_minutes() -> None:
    assert NOTIFICATION_TIMEFRAMES == ("15m", "1h", "4h")
    assert notification_window_is_ready("15m", HISTORY_BARS)
    assert not notification_window_is_ready("15m", HISTORY_BARS + 1)
    assert notification_window_is_ready("4h", HISTORY_BARS + 100)


def test_pattern_009_reaches_four_hour_notification_output_at_right_edge() -> None:
    timeframe = "4h"
    length = 250
    bars = channel_bars(timeframe, length, (5, 100, 249), (50, 180))

    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", timeframe, bars)
        if item.pattern.pattern_id == "PATTERN_009"
    )

    assert match.timeframe == timeframe
    assert match.anchors[-1].index == length - 1
    assert [anchor.label for anchor in match.anchors] == [
        "U1",
        "U2",
        "L1",
        "L2",
        "L3",
    ]
    assert f"周期: {timeframe}" in telegram_caption(match, bars)
    assert f"样本: 最近{length}根已收盘K线" in telegram_caption(match, bars)


@pytest.mark.parametrize("timeframe", ["15m", "1h"])
def test_pattern_009_is_not_detected_on_short_timeframes(timeframe: str) -> None:
    bars = channel_bars(timeframe, 201, (5, 80, 200), (40, 150))

    matches = NotificationPatternScanner().scan("TEST", timeframe, bars)

    assert all(item.pattern.pattern_id != "PATTERN_009" for item in matches)


def test_extended_four_hour_channel_keeps_four_hour_geometry() -> None:
    bars = channel_bars("4h", 250, (5, 100, 249), (50, 180))
    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", "4h", bars)
        if item.pattern.pattern_id == "PATTERN_009"
    )

    assert match.timeframe == "4h"
    assert match.pattern.features["channel_span"].value == 244.0
    assert pattern_line_groups(match.pattern, bars, 0) == (
        (
            match.pattern.geometry["upper_line"]["start"],
            match.pattern.geometry["upper_line"]["end"],
        ),
        (
            match.pattern.geometry["lower_line"]["start"],
            match.pattern.geometry["lower_line"]["end"],
        ),
    )


def test_existing_patterns_keep_a_201_bar_window_inside_extended_four_hour_data() -> None:
    visible = near_bars()
    fixed = [visible[0]] * (HISTORY_BARS - len(visible)) + visible
    bars = [fixed[0]] * 49 + fixed

    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", "4h", bars)
        if item.pattern.pattern_id == "PATTERN_002"
    )

    assert max(anchor.index for anchor in match.anchors) == len(bars) - 1
    assert match.pattern.metadata["notification_window_start_index"] == 49
