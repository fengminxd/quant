from __future__ import annotations

from features.basic import higher_low_score, resistance_flatness, volume_contraction
from indicators.swing import Pivot

from tests.conftest import make_bar


def test_higher_low_score_rewards_rising_lows() -> None:
    lows = [
        Pivot(1, 2, 10.0, "low"),
        Pivot(6, 7, 11.0, "low"),
        Pivot(12, 13, 12.0, "low"),
    ]

    assert higher_low_score(lows).value == 100.0


def test_resistance_flatness_scores_tight_highs() -> None:
    highs = [
        Pivot(2, 3, 20.0, "high"),
        Pivot(8, 9, 20.1, "high"),
        Pivot(14, 15, 19.9, "high"),
    ]

    assert resistance_flatness(highs, atr_value=1.0).value > 70.0


def test_volume_contraction_detects_declining_participation() -> None:
    data = [
        make_bar(i, 10 + i * 0.1, 9 + i * 0.1)
        for i in range(10)
    ]

    assert volume_contraction(data, lookback=10).value > 0.0
