"""Reproduce the MUUSDT 4h bearish-continuation triangle reference case."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from math import isclose

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from factors.triangle_context import TriangleBearishContinuationScore
from factors.trade_feasibility import PatternTradeFeasibilityScorer
from features.triangle_context import bearish_triangle_continuation_features
from patterns import PatternDetector, Triangle

LOGGER = logging.getLogger(__name__)


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


async def validate() -> None:
    """Fetch Binance bars and validate geometry, EMA rejection, and context."""

    candles = await BinanceFuturesClient().fetch_klines(
        SymbolConfig("MU", "MUUSDT"),
        "4h",
        600,
        _timestamp("2026-04-15 00:00"),
        _timestamp("2026-07-15 00:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    signal_at = _timestamp("2026-07-15 00:00")
    as_of_index = next(
        index for index, bar in enumerate(bars) if bar.timestamp == signal_at
    )
    poll = PatternDetector([Triangle()]).poll_at(bars, "4h", as_of_index)
    pattern = poll[0].pattern
    features = bearish_triangle_continuation_features(bars, pattern)
    factor = TriangleBearishContinuationScore().calculate(features)
    feasibility = PatternTradeFeasibilityScorer().score(pattern, bars)

    assert pattern.detected
    assert pattern.geometry["upper_timestamps"] == [
        _timestamp("2026-07-05 12:00"),
        _timestamp("2026-07-09 12:00"),
        _timestamp("2026-07-15 00:00"),
    ]
    assert pattern.geometry["lower_timestamps"] == [
        _timestamp("2026-07-08 08:00"),
        _timestamp("2026-07-13 12:00"),
    ]
    assert pattern.metadata["structure_span_bars"] == 57
    assert pattern.metadata["upper_confirmation_count"] == 3
    assert pattern.metadata["lower_confirmation_count"] == 2
    assert pattern.metadata["confirmation_cluster_bars"] == 5
    assert isclose(features["upper_third_ema99_value"].value, 1001.2692268, abs_tol=1e-7)
    assert features["upper_third_ema_wick_rejection"].value == 1.0
    assert factor.metadata["state"] == "bearish_continuation_entry_candidate"
    assert factor.metadata["downside_break_required"] is False
    assert isclose(factor.score, 76.3654, abs_tol=1e-4)
    assert feasibility.plan is not None
    assert feasibility.plan.entry_price == 1000.30
    assert feasibility.factor.metadata["feasible"] is True
    LOGGER.info(
        "MUUSDT 4h validated: triangle=%.4f continuation=%.4f ema99=%.8f",
        pattern.score,
        factor.score,
        features["upper_third_ema99_value"].value,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
