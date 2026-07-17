"""Audit the reported SOLUSDT 1h head-and-shoulders-top window."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from math import isclose

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from features.ema_rejection import upper_ema_wick_rejection_at_close
from indicators.ema import exponential_moving_average
from patterns.detector import PatternDetector
from patterns.head_shoulders_top import HeadAndShouldersTop

LOGGER = logging.getLogger(__name__)
UTC_PLUS_8 = timezone(timedelta(hours=8))


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)
    return int(parsed.timestamp() * 1000)


async def validate() -> None:
    """Fetch Binance bars and separate EMA rejection from Swing confirmation."""

    candles = await BinanceFuturesClient().fetch_klines(
        SymbolConfig("SOL", "SOLUSDT"),
        "1h",
        2_000,
        _timestamp("2026-05-01 00:00"),
        _timestamp("2026-07-12 10:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    indexes = {bar.timestamp: index for index, bar in enumerate(bars)}
    start = indexes[_timestamp("2026-07-09 09:00")]
    right_shoulder = indexes[_timestamp("2026-07-11 23:00")]
    confirmed = indexes[_timestamp("2026-07-12 04:00")]
    breakdown = indexes[_timestamp("2026-07-12 07:00")]

    right_shoulder_window = bars[: right_shoulder + 1]
    right_shoulder_bar = bars[right_shoulder]
    ema99 = exponential_moving_average(right_shoulder_window, 99)[-1]
    assert isclose(ema99, 78.5559410321, abs_tol=1e-10)
    assert right_shoulder_bar.high > ema99 > max(
        right_shoulder_bar.open,
        right_shoulder_bar.close,
    )
    assert upper_ema_wick_rejection_at_close(right_shoulder_window)

    detector = HeadAndShouldersTop()
    assert not detector.detect(bars[start : right_shoulder + 1]).detected
    structure = detector.detect(bars[start : confirmed + 1])
    assert structure.detected
    assert structure.metadata["state"] == "structure_confirmed"
    assert structure.geometry["point_timestamps"] == [
        _timestamp("2026-07-09 15:00"),
        _timestamp("2026-07-10 18:00"),
        _timestamp("2026-07-11 23:00"),
    ]
    assert isclose(structure.score, 81.982, abs_tol=1e-4)

    confirmed_breakdown = detector.detect(bars[start : breakdown + 1])
    assert confirmed_breakdown.geometry["breakdown_timestamp"] == _timestamp(
        "2026-07-12 07:00"
    )
    assert isclose(confirmed_breakdown.score, 96.982, abs_tol=1e-4)
    production = PatternDetector([detector]).poll_at(bars, "1h", breakdown)
    assert production
    assert production[0].pattern.geometry["point_timestamps"] != structure.geometry[
        "point_timestamps"
    ]
    LOGGER.info(
        "SOLUSDT audited: right-shoulder=23:00 EMA99=%.8f "
        "structure=%.4f breakdown=%.4f production-selected=%s",
        ema99,
        structure.score,
        confirmed_breakdown.score,
        production[0].pattern.geometry["point_timestamps"],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
