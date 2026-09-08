"""Notification regressions for distinct breakout and retest events."""

from __future__ import annotations

from core.models import Bar
from notifications.config import HISTORY_BARS
from notifications.scanner import NotificationPatternScanner


def _notification_bars(*, breakout_index: int) -> list[Bar]:
    """Build one right-edge support contact with a configurable breakout."""

    visible = [
        Bar(index, 19.7, 19.9, 19.5, 19.8, 1_000.0, "1h")
        for index in range(56)
    ]
    visible[5] = Bar(5, 20.0, 23.0, 19.5, 19.8, 1_000.0, "1h")
    visible[breakout_index] = Bar(
        breakout_index,
        19.8,
        20.5,
        19.7,
        20.3,
        1_000.0,
        "1h",
    )
    for index in range(breakout_index + 1, 55):
        visible[index] = Bar(
            index,
            20.2,
            20.4,
            20.0,
            20.25,
            1_000.0,
            "1h",
        )
    visible[55] = Bar(55, 20.5, 20.8, 19.7, 20.2, 1_000.0, "1h")
    prefix = [visible[0]] * (HISTORY_BARS - len(visible))
    return [*prefix, *visible]


def _pattern_004_rules(bars: list[Bar]) -> list[str]:
    return [
        match.rule
        for match in NotificationPatternScanner().scan("TEST", "1h", bars)
        if match.pattern.pattern_id == "PATTERN_004"
    ]


def test_notification_rejects_breakout_on_the_retest_candle() -> None:
    bars = _notification_bars(breakout_index=55)

    assert "breakout_retest" not in _pattern_004_rules(bars)


def test_notification_rejects_breakout_immediately_before_retest() -> None:
    bars = _notification_bars(breakout_index=54)

    assert "breakout_retest" not in _pattern_004_rules(bars)


def test_notification_accepts_one_complete_candle_between_events() -> None:
    bars = _notification_bars(breakout_index=53)

    match = next(
        match
        for match in NotificationPatternScanner().scan("TEST", "1h", bars)
        if match.pattern.pattern_id == "PATTERN_004"
        and match.rule == "breakout_retest"
    )

    assert match.pattern.features["breakout_retest_gap_bars"].value == 1.0
