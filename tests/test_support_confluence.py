from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.models import Bar
from factors import SupportConfluenceScorer
from indicators.swing import PivotDetector, SwingDetector
from patterns import HorizontalSupport, ThreePointTrendlineSupport


def hype_1h_confluence_bars() -> list[Bar]:
    """Offline HYPE-shaped fixture for the user-reported UTC+8 event times."""

    origin = datetime(2026, 5, 12, 21)
    p1, resistance, p2, breakout, p3 = 100, 128, 146, 154, 179
    bars: list[Bar] = []
    for index in range(p3 + 3):
        if index < p1:
            close = 37.8 + index * 0.035
        elif index <= resistance:
            support = 40.649 + (44.18 - 40.649) * (index - p1) / (p2 - p1)
            close = support + 1.0 + (index - p1) * 0.11
        elif index <= p2:
            close = 46.9 - (index - resistance) * 0.12
        elif index < breakout:
            close = 44.8 + (index - p2) * 0.34
        else:
            close = 47.55 + (index - breakout) * 0.015
        open_price = close - 0.08
        low = open_price - 0.22
        high = close + 0.25
        if index == p1:
            open_price, high, low, close = 40.833, 41.193, 40.649, 40.904
        elif index == resistance:
            open_price, high, low, close = 46.417, 47.275, 46.349, 47.004
        elif index == p2:
            open_price, high, low, close = 44.687, 45.297, 44.180, 44.747
        elif index == breakout:
            open_price, high, low, close = 46.95, 47.85, 46.85, 47.70
        elif index == p3:
            open_price, high, low, close = 48.036, 48.069, 47.063, 47.614
        elif index > p3:
            open_price, high, low, close = 47.70, 48.05, 47.35, 47.90
        bars.append(
            Bar(
                (origin + index * timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
                open_price,
                high,
                low,
                close,
                500_000.0,
                "1h",
            )
        )
    return bars


def scorer() -> SupportConfluenceScorer:
    swing = SwingDetector(PivotDetector(left=2, right=2), min_bars=1)
    trendline = ThreePointTrendlineSupport(swing)
    horizontal = HorizontalSupport(swing)
    return SupportConfluenceScorer(trendline, horizontal)


def test_hype_support_confluence_scores_high_after_confirmation() -> None:
    bars = hype_1h_confluence_bars()
    event_index = 179

    evaluation = scorer().evaluate(bars, event_index)

    assert evaluation.trendline.detected is True
    assert evaluation.trendline.geometry["point_timestamps"] == [
        "2026-05-17 01:00",
        "2026-05-18 23:00",
        "2026-05-20 08:00",
    ]
    assert evaluation.horizontal.detected is True
    assert evaluation.horizontal.metadata["rule_type"] == "breakout_retest"
    assert evaluation.horizontal.geometry["point_timestamps"] == [
        "2026-05-18 05:00",
        "2026-05-20 08:00",
    ]
    assert evaluation.factor.features["shared_anchor"] == 1.0
    assert evaluation.factor.features["resistance_reclaim_distance_atr"] > 0.0
    assert evaluation.factor.features["event_close_above_ema99"] == 1.0
    assert evaluation.factor.metadata["confirmation_lag_bars"] == 2
    assert evaluation.factor.score >= 80.0


def test_confluence_is_unavailable_at_unconfirmed_third_point_close() -> None:
    bars = hype_1h_confluence_bars()
    event_index = 179

    at_close = scorer().evaluate(bars, event_index, as_of_index=event_index)
    confirmed = scorer().evaluate(bars, event_index, as_of_index=event_index + 2)

    assert at_close.trendline.detected is False
    assert at_close.factor.score == 0.0
    assert confirmed.factor.score >= 80.0


def test_confluence_gate_rejects_close_below_reclaimed_resistance() -> None:
    bars = hype_1h_confluence_bars()
    event = bars[179]
    bars[179] = Bar(
        event.timestamp,
        47.10,
        47.20,
        event.low,
        47.12,
        event.volume,
        event.timeframe,
    )

    evaluation = scorer().evaluate(bars, 179)

    assert evaluation.factor.score == 0.0
    assert evaluation.factor.metadata["gate_passed"] is False


def test_confluence_indexes_must_be_causal() -> None:
    bars = hype_1h_confluence_bars()

    with pytest.raises(ValueError, match="must include the event"):
        scorer().evaluate(bars, 179, as_of_index=178)
