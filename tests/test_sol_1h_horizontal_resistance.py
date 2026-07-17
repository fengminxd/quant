from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Bar
from patterns.horizontal_resistance import HorizontalResistance


FIXTURE = Path(__file__).parent / "fixtures" / "sol_1h_horizontal_resistance.json"
LEFT_ANCHOR = 1_783_137_600_000  # 2026-07-04 12:00 UTC+8
RIGHT_ANCHOR = 1_783_371_600_000  # 2026-07-07 05:00 UTC+8
CONFIRMED_AT = 1_783_378_800_000  # 2026-07-07 07:00 UTC+8


def sol_bars() -> list[Bar]:
    """Load the Binance USD-M SOLUSDT horizontal-resistance window."""

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Bar(row[0], *row[1:], "1h") for row in rows]


def test_sol_two_swing_highs_form_horizontal_resistance() -> None:
    result = HorizontalResistance().detect(sol_bars())

    assert result.detected is True
    assert result.geometry["point_timestamps"] == [LEFT_ANCHOR, RIGHT_ANCHOR]
    assert result.geometry["swing_highs"] == [
        (2, pytest.approx(83.96)),
        (67, pytest.approx(83.75)),
    ]
    assert result.geometry["level"] == pytest.approx(83.75)
    assert result.metadata["contact_types"] == ("upper_shadow", "upper_shadow")
    assert result.metadata["detected_at_index"] == 69
    assert sol_bars()[69].timestamp == CONFIRMED_AT
    assert result.score == pytest.approx(81.4977, abs=1e-4)


def test_sol_resistance_has_no_intermediate_price_acceptance_above_level() -> None:
    bars = sol_bars()
    result = HorizontalResistance().detect(bars)
    middle = bars[3:67]

    assert max(bar.high for bar in middle) == pytest.approx(83.57)
    assert max(bar.open for bar in middle) == pytest.approx(83.44)
    assert max(bar.open for bar in middle) > bars[67].open
    assert max(bar.open for bar in middle) < result.geometry["level"]
    assert result.features["span"].value == 65.0
    assert result.features["penetration_count"].value == 0.0
    assert result.features["open_violation_count"].value == 0.0
    assert result.features["anchor_overshoot_atr"].value == pytest.approx(
        0.2207207207,
        abs=1e-10,
    )


def test_sol_second_anchor_requires_two_right_side_confirmation_bars() -> None:
    bars = sol_bars()
    detector = HorizontalResistance()

    assert detector.detect(bars[:68]).detected is False
    assert detector.detect(bars[:69]).detected is False
    assert detector.detect(bars[:70]).detected is True
