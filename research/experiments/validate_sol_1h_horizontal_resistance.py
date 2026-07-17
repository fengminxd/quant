"""Reproduce the reported SOLUSDT 1h horizontal-resistance case."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from math import isclose

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from patterns.horizontal_resistance import HorizontalResistance

LOGGER = logging.getLogger(__name__)
UTC_PLUS_8 = timezone(timedelta(hours=8))


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)
    return int(parsed.timestamp() * 1000)


async def validate() -> None:
    """Fetch Binance bars and validate both resistance anchors causally."""

    candles = await BinanceFuturesClient().fetch_klines(
        SymbolConfig("SOL", "SOLUSDT"),
        "1h",
        100,
        _timestamp("2026-07-04 10:00"),
        _timestamp("2026-07-07 07:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    result = HorizontalResistance().detect(bars)

    assert result.detected
    assert result.geometry["point_timestamps"] == [
        _timestamp("2026-07-04 12:00"),
        _timestamp("2026-07-07 05:00"),
    ]
    assert result.geometry["swing_highs"] == [(2, 83.96), (67, 83.75)]
    assert isclose(result.geometry["level"], 83.75, abs_tol=1e-10)
    assert result.metadata["detected_at_index"] == 69
    assert bars[69].timestamp == _timestamp("2026-07-07 07:00")
    assert result.features["span"].value == 65.0
    assert result.features["penetration_count"].value == 0.0
    assert result.features["open_violation_count"].value == 0.0
    assert isclose(result.score, 81.4977, abs_tol=1e-4)
    LOGGER.info(
        "SOLUSDT horizontal resistance validated: level=%.2f span=%.0f score=%.4f",
        result.geometry["level"],
        result.features["span"].value,
        result.score,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
