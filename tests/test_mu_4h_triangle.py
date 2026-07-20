from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Bar
from factors.triangle_context import TriangleBearishContinuationScore
from factors.trade_feasibility import PatternTradeFeasibilityScorer
from features.triangle_context import bearish_triangle_continuation_features
from patterns import PatternDetector, Triangle


FIXTURE = Path(__file__).parent / "fixtures" / "mu_4h_triangle.json"
START = 1_783_252_800_000  # 2026-07-05 20:00 UTC+8
DECLINE_START = 1_782_388_800_000  # 2026-06-25 20:00 UTC+8
UPPER_THIRD = 1_784_073_600_000  # 2026-07-15 08:00 UTC+8
CONFIRMED_AT = 1_784_102_400_000  # 2026-07-15 16:00 UTC+8


def mu_bars() -> list[Bar]:
    """Load Binance USD-M MUUSDT 4h OHLCV through swing confirmation."""

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Bar(row[0], *row[1:], "4h") for row in rows]


def context_triangle() -> Triangle:
    """Retain the old MU geometry for factor tests without the new leg gate."""

    return Triangle(min_adjacent_anchor_span=1)


def test_mu_triangle_is_rejected_by_production_leg_span() -> None:
    bars = mu_bars()

    assert PatternDetector([Triangle()]).poll_at(bars, "4h", len(bars) - 1) == []


def test_mu_reference_geometry_is_available_with_relaxed_leg_span() -> None:
    bars = mu_bars()
    result = PatternDetector([context_triangle()]).poll_at(
        bars, "4h", len(bars) - 1
    )[0].pattern
    timestamps = {bar.timestamp: index for index, bar in enumerate(bars)}

    assert bars[-1].timestamp == CONFIRMED_AT
    assert timestamps[UPPER_THIRD] - timestamps[START] == 57
    assert result.detected is True
    assert result.metadata["triangle_type"] == "symmetrical_triangle"
    assert result.metadata["state"] == "structure_confirmed"
    assert result.metadata["structure_span_bars"] == 57
    assert result.metadata["upper_confirmation_count"] == 3
    assert result.metadata["lower_confirmation_count"] == 2
    assert result.metadata["confirmation_cluster_bars"] == 5
    assert result.geometry["upper_timestamps"] == [
        START,
        1_783_598_400_000,
        UPPER_THIRD,
    ]
    assert result.geometry["upper_points"][-1][1] == pytest.approx(1006.18)
    assert result.geometry["lower_timestamps"] == [
        1_783_497_600_000,
        1_783_944_000_000,
    ]


def test_mu_upper_third_wick_rejects_ema99_and_context_is_bearish() -> None:
    bars = mu_bars()
    result = PatternDetector([context_triangle()]).poll(bars_by_timeframe(bars))[0].pattern
    features = bearish_triangle_continuation_features(bars, result)
    factor = TriangleBearishContinuationScore().calculate(features)
    target = next(bar for bar in bars if bar.timestamp == UPPER_THIRD)
    ema99 = features["upper_third_ema99_value"].value

    assert ema99 == pytest.approx(1001.2692268, abs=1e-7)
    assert target.high > ema99 > max(target.open, target.close)
    assert target.close < ema99
    assert features["upper_third_ema_wick_rejection"].value == 1.0
    assert features["prior_lower_high_ratio"].value == pytest.approx(0.75)
    assert features["prior_decline_atr"].value == pytest.approx(16.2273565, abs=1e-7)
    assert features["prior_decline_start_index"].metadata["timestamp"] == DECLINE_START
    assert features["prior_ema99_slope_atr"].value < 0.0
    assert features["prior_ema99_above_close_ratio"].value == 0.0
    assert factor.score == pytest.approx(76.3654, abs=1e-4)
    assert factor.metadata["active"] is True
    assert factor.metadata["state"] == "bearish_continuation_entry_candidate"
    assert factor.metadata["confirmation"] == "third_upper_ema_rejection"
    assert factor.metadata["downside_break_required"] is False

    feasibility = PatternTradeFeasibilityScorer().score(result, bars)
    assert feasibility.plan is not None
    assert feasibility.plan.direction == "bearish"
    assert feasibility.plan.entry_index == next(
        index for index, bar in enumerate(bars) if bar.timestamp == UPPER_THIRD
    )
    assert feasibility.plan.entry_price == pytest.approx(1000.30)
    assert feasibility.plan.stop_price == pytest.approx(1013.4755861, abs=1e-7)
    assert feasibility.plan.target_price == pytest.approx(911.6441935, abs=1e-7)
    assert feasibility.factor.score == 100.0
    assert feasibility.factor.metadata["active"] is True
    assert feasibility.factor.metadata["feasible"] is True
    assert feasibility.factor.metadata["net_reward_risk"] == pytest.approx(5.986704)
    assert feasibility.factor.metadata["downside_break_required"] is False


def test_mu_third_upper_contact_is_actionable_at_its_close_without_future() -> None:
    bars = mu_bars()
    target = next(index for index, bar in enumerate(bars) if bar.timestamp == UPPER_THIRD)
    detector = PatternDetector([context_triangle()])
    before = detector.poll_at(bars, "4h", target - 1)[0].pattern
    at_close = detector.poll_at(bars, "4h", target)[0].pattern
    next_poll = detector.poll_at(bars, "4h", target + 1)[0].pattern

    assert before.geometry["upper_timestamps"][-1] != UPPER_THIRD
    assert at_close.geometry["upper_timestamps"][-1] == UPPER_THIRD
    assert next_poll.geometry["upper_timestamps"][-1] == UPPER_THIRD
    assert at_close.metadata["detected_at_index"] + at_close.metadata[
        "window_start_index"
    ] == target
    before_trade = PatternTradeFeasibilityScorer().score(
        before, bars, as_of_index=target - 1
    )
    at_close_trade = PatternTradeFeasibilityScorer().score(
        at_close, bars, as_of_index=target
    )
    assert before_trade.plan is None
    assert at_close_trade.plan is not None
    assert at_close_trade.plan.entry_index == target
    assert at_close_trade.factor.metadata["feasible"] is True

    original = bearish_triangle_continuation_features(bars, at_close)
    changed = list(bars)
    changed[target + 1] = Bar(
        changed[target + 1].timestamp,
        2000.0,
        2100.0,
        1900.0,
        2050.0,
        changed[target + 1].volume,
        "4h",
    )
    changed[target + 2] = Bar(
        changed[target + 2].timestamp,
        1800.0,
        1900.0,
        1700.0,
        1750.0,
        changed[target + 2].volume,
        "4h",
    )
    recalculated = bearish_triangle_continuation_features(changed, at_close)

    assert recalculated == original


def bars_by_timeframe(bars: list[Bar]) -> dict[str, list[Bar]]:
    return {"4h": bars}
