from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Bar
from features.ema_rejection import upper_ema_wick_rejection_at_close
from indicators.ema import exponential_moving_average
from patterns.head_shoulders_top import HeadAndShouldersTop


FIXTURE = Path(__file__).parent / "fixtures" / "sol_1h_head_shoulders_top.json"
PATTERN_START = 1_783_558_800_000  # 2026-07-09 09:00 UTC+8
LEFT_SHOULDER = 1_783_580_400_000  # 2026-07-09 15:00 UTC+8
HEAD = 1_783_677_600_000  # 2026-07-10 18:00 UTC+8
RIGHT_SHOULDER = 1_783_782_000_000  # 2026-07-11 23:00 UTC+8
STRUCTURE_CONFIRMED_AT = 1_783_800_000_000  # 2026-07-12 04:00 UTC+8
BREAKDOWN_AT = 1_783_810_800_000  # 2026-07-12 07:00 UTC+8
EMA99_BEFORE_FIXTURE = 80.75024052778485


def sol_bars() -> list[Bar]:
    """Load the Binance USD-M SOLUSDT 1h regression window."""

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Bar(row[0], *row[1:], "1h") for row in rows]


def _index(bars: list[Bar], timestamp: int) -> int:
    return next(index for index, bar in enumerate(bars) if bar.timestamp == timestamp)


def _pattern_window(bars: list[Bar], end: int) -> list[Bar]:
    return bars[_index(bars, PATTERN_START) : _index(bars, end) + 1]


def test_right_shoulder_2300_bar_wick_rejects_causal_ema99() -> None:
    bars = sol_bars()
    event_index = _index(bars, RIGHT_SHOULDER)
    visible = bars[: event_index + 1]
    event = visible[-1]
    ema99 = exponential_moving_average(
        visible,
        99,
        initial_value=EMA99_BEFORE_FIXTURE,
    )[-1]

    assert len(visible) == 100
    assert ema99 == pytest.approx(78.5559410321, abs=1e-10)
    assert event.open == pytest.approx(78.44)
    assert event.high == pytest.approx(78.86)
    assert event.close == pytest.approx(78.34)
    assert event.high > ema99 > max(event.open, event.close)
    assert upper_ema_wick_rejection_at_close(
        visible,
        initial_ema=EMA99_BEFORE_FIXTURE,
    ) is True


def test_strict_swing_rule_does_not_confirm_the_structure_at_right_shoulder_close() -> None:
    bars = sol_bars()
    detector = HeadAndShouldersTop()

    assert detector.detect(_pattern_window(bars, RIGHT_SHOULDER)).detected is False
    assert detector.detect(_pattern_window(bars, STRUCTURE_CONFIRMED_AT - 3_600_000)).detected is False


def test_next_bar_is_the_strict_right_shoulder_and_confirms_five_bars_later() -> None:
    bars = sol_bars()
    result = HeadAndShouldersTop().detect(
        _pattern_window(bars, STRUCTURE_CONFIRMED_AT)
    )

    assert result.detected is True
    assert result.metadata["state"] == "structure_confirmed"
    assert result.metadata["detected_at_index"] == len(
        _pattern_window(bars, STRUCTURE_CONFIRMED_AT)
    ) - 1
    assert result.geometry["point_timestamps"] == [
        LEFT_SHOULDER,
        HEAD,
        RIGHT_SHOULDER,
    ]
    assert result.geometry["points"] == [
        (6, pytest.approx(78.82)),
        (33, pytest.approx(79.64)),
        (62, pytest.approx(78.86)),
    ]
    assert result.geometry["neckline_timestamps"] == [
        1_783_598_400_000,  # 2026-07-09 20:00 UTC+8
        1_783_731_600_000,  # 2026-07-11 09:00 UTC+8
    ]
    assert result.features["span"].value == 56.0
    assert result.features["confirmation_lag"].value == 5.0
    assert result.score == pytest.approx(81.982, abs=1e-4)


def test_neckline_breakdown_is_confirmed_after_the_structure() -> None:
    bars = sol_bars()
    result = HeadAndShouldersTop().detect(_pattern_window(bars, BREAKDOWN_AT))

    assert result.detected is True
    assert result.metadata["state"] == "breakdown_confirmed"
    assert result.geometry["breakdown_timestamp"] == BREAKDOWN_AT
    assert result.features["breakdown_confirmed"].value == 1.0
    assert result.score == pytest.approx(96.982, abs=1e-4)
