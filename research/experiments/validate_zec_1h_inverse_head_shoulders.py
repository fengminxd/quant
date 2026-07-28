"""Audit why the former ZECUSDT 1h PATTERN_007 case is now invalid."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from indicators.swing import Pivot
from patterns.inverse_head_shoulders_geometry import valid_leg_spans

LOGGER = logging.getLogger(__name__)


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


async def validate() -> None:
    """Verify that the shorter leg is below two-thirds of the longer leg."""

    symbol = SymbolConfig(name="ZEC", exchange_symbol="ZECUSDT", enabled=True)
    candles = await BinanceFuturesClient().fetch_klines(
        symbol,
        "1h",
        700,
        _timestamp("2026-06-15 00:00"),
        _timestamp("2026-07-02 00:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    anchor_times = (
        _timestamp("2026-06-25 13:00"),
        _timestamp("2026-06-28 22:00"),
        _timestamp("2026-07-01 01:00"),
    )
    indexes = [
        next(index for index, bar in enumerate(bars) if bar.timestamp == timestamp)
        for timestamp in anchor_times
    ]
    anchors = tuple(
        Pivot(index, index + 5, bars[index].low, "low") for index in indexes
    )
    left_leg = anchors[1].index - anchors[0].index
    right_leg = anchors[2].index - anchors[1].index
    assert not valid_leg_spans(
        *anchors,
        min_span=40,
        min_leg_span=10,
        min_leg_span_ratio=2.0 / 3.0,
    )
    LOGGER.info(
        "ZECUSDT legacy PATTERN_007 rejected: left_leg=%d right_leg=%d difference=%d",
        left_leg,
        right_leg,
        abs(left_leg - right_leg),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
