"""Reproduce the reported BTCUSDT 4h three-point resistance line."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from math import isclose

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from patterns.three_point_trendline_resistance import ThreePointTrendlineResistance

LOGGER = logging.getLogger(__name__)
UTC_PLUS_8 = timezone(timedelta(hours=8))


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)
    return int(parsed.timestamp() * 1000)


async def validate() -> None:
    """Fetch Binance bars and validate the confirmed descending resistance."""

    candles = await BinanceFuturesClient().fetch_klines(
        SymbolConfig("BTC", "BTCUSDT"),
        "4h",
        100,
        _timestamp("2026-05-05 00:00"),
        _timestamp("2026-05-15 08:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    result = ThreePointTrendlineResistance().detect(bars)

    assert result.detected
    assert result.geometry["point_timestamps"] == [
        _timestamp("2026-05-06 16:00"),
        _timestamp("2026-05-11 04:00"),
        _timestamp("2026-05-15 00:00"),
    ]
    assert result.features["line_span"].value == 50.0
    assert result.features["leg_1_span"].value == 27.0
    assert result.features["leg_2_span"].value == 23.0
    assert result.features["body_violation_count"].value == 0.0
    assert isclose(result.features["fit_error_atr"].value, 0.028592054, abs_tol=1e-9)
    assert isclose(result.score, 94.2852, abs_tol=1e-4)
    LOGGER.info(
        "BTCUSDT 4h resistance validated: slope=%.3f span=%.0f score=%.4f",
        result.features["line_slope"].value,
        result.features["line_span"].value,
        result.score,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
