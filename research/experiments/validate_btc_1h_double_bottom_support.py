"""Reproduce the reported BTCUSDT 1h double-bottom support case."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from math import isclose

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from patterns.horizontal_support import HorizontalSupport

LOGGER = logging.getLogger(__name__)
UTC_PLUS_8 = timezone(timedelta(hours=8))


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)
    return int(parsed.timestamp() * 1000)


async def validate() -> None:
    """Fetch Binance bars and validate the confirmed BTC double bottom."""

    candles = await BinanceFuturesClient().fetch_klines(
        SymbolConfig("BTC", "BTCUSDT"),
        "1h",
        300,
        _timestamp("2026-06-25 16:00"),
        _timestamp("2026-07-01 14:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    result = HorizontalSupport().detect(bars)

    assert result.detected
    assert result.metadata["rule_type"] == "double_swing_low"
    assert result.geometry["point_timestamps"] == [
        _timestamp("2026-06-25 21:00"),
        _timestamp("2026-07-01 09:00"),
    ]
    assert isclose(result.geometry["level"], 57_894.3, abs_tol=1e-10)
    assert result.features["span"].value == 132.0
    assert min(bar.close for bar in bars[6:137]) > result.geometry["level"]
    assert result.metadata["detected_at_index"] == 142
    assert bars[142].timestamp == _timestamp("2026-07-01 14:00")
    assert isclose(result.score, 96.744, abs_tol=1e-4)
    LOGGER.info(
        "BTCUSDT double bottom validated: level=%.1f span=%.0f score=%.4f",
        result.geometry["level"],
        result.features["span"].value,
        result.score,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
