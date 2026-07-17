from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Bar
from patterns.three_point_trendline_resistance import ThreePointTrendlineResistance


FIXTURE = Path(__file__).parent / "fixtures" / "btc_4h_three_point_resistance.json"
P1 = 1_778_054_400_000  # 2026-05-06 16:00 UTC+8
P2 = 1_778_443_200_000  # 2026-05-11 04:00 UTC+8
P3 = 1_778_774_400_000  # 2026-05-15 00:00 UTC+8
P3_CONFIRMED_AT = 1_778_803_200_000  # 2026-05-15 08:00 UTC+8


def btc_bars() -> list[Bar]:
    """Load the Binance USD-M BTCUSDT 4h resistance-line window."""

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Bar(row[0], *row[1:], "4h") for row in rows]


def test_btc_three_swing_highs_form_descending_resistance() -> None:
    bars = btc_bars()
    result = ThreePointTrendlineResistance().detect(bars)

    assert result.detected is True
    assert result.geometry["point_timestamps"] == [P1, P2, P3]
    assert result.geometry["points"] == [
        (10, pytest.approx(82_828.7)),
        (37, pytest.approx(82_460.5)),
        (60, pytest.approx(81_999.0)),
    ]
    assert bars[62].timestamp == P3_CONFIRMED_AT
    assert result.features["line_span"].value == 50.0
    assert result.features["leg_1_span"].value == 27.0
    assert result.features["leg_2_span"].value == 23.0
    assert result.features["line_slope"].value == pytest.approx(-16.594)
    assert result.features["body_violation_count"].value == 0.0
    assert result.score == pytest.approx(94.2852, abs=1e-4)


def test_btc_third_pivot_is_retained_despite_nearby_opposite_swing() -> None:
    result = ThreePointTrendlineResistance().detect(btc_bars())

    assert result.detected is True
    assert result.features["fit_error_atr"].value == pytest.approx(
        0.028592054,
        abs=1e-9,
    )
    assert result.features["upper_shadow_cross_count"].value == 3.0
    assert result.metadata["valid_triplet_count"] == 1
