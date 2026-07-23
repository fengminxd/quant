from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Bar
from patterns.horizontal_support import HorizontalSupport


FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_double_bottom_support.json"
LEFT_ANCHOR = 1_782_392_400_000  # 2026-06-25 21:00 UTC+8
RIGHT_ANCHOR = 1_782_867_600_000  # 2026-07-01 09:00 UTC+8
CONFIRMED_AT = 1_782_885_600_000  # 2026-07-01 14:00 UTC+8


def btc_bars() -> list[Bar]:
    """Load the Binance USD-M BTCUSDT 1h double-bottom window."""

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Bar(row[0], *row[1:], "1h") for row in rows]


def test_btc_two_swing_lows_form_confirmed_double_bottom_support() -> None:
    bars = btc_bars()
    result = HorizontalSupport().detect(bars)

    assert result.detected is True
    assert result.metadata["rule_type"] == "double_swing_low"
    assert result.metadata["detected_at_index"] == 142
    assert bars[142].timestamp == CONFIRMED_AT
    assert result.geometry["point_timestamps"] == [LEFT_ANCHOR, RIGHT_ANCHOR]
    assert result.geometry["points"] == [
        (5, pytest.approx(58_030.0)),
        (137, pytest.approx(57_758.6)),
    ]
    assert result.geometry["level"] == pytest.approx(58_139.2)
    assert result.score == 100.0


def test_btc_intermediate_closes_stay_strictly_above_common_support() -> None:
    bars = btc_bars()
    result = HorizontalSupport().detect(bars)
    intermediate = bars[6:137]

    assert result.features["span"].value == 132.0
    assert min(bar.close for bar in intermediate) == pytest.approx(58_356.2)
    assert all(bar.close > result.geometry["level"] for bar in intermediate)
    assert result.features["level_error"].value == 0.0
    assert result.features["level_error_atr"].value == 0.0
    assert result.features["contact_overlap_atr"].value == pytest.approx(
        0.4491714655,
        abs=1e-10,
    )
    assert result.features["breakout_index"].value == -1.0
