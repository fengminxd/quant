"""Reproduce the reported ZECUSDT 1h inverse-head-and-shoulders case."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from math import isclose

from data.binance_futures import BinanceFuturesClient
from data.market_config import SymbolConfig
from factors.support_lineage import SupportLineageScore
from features.pattern_lineage import support_lineage_features
from patterns.horizontal_support import HorizontalSupport
from patterns.inverse_head_shoulders import InverseHeadShoulders
from patterns.three_point_trendline_support import ThreePointTrendlineSupport

LOGGER = logging.getLogger(__name__)


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _utc_plus_8(value: int) -> str:
    parsed = datetime.fromtimestamp(value / 1000, timezone.utc) + timedelta(hours=8)
    return parsed.strftime("%Y-%m-%d %H:%M")


async def validate() -> None:
    """Fetch the public market window and validate exact structural geometry."""

    symbol = SymbolConfig(name="ZEC", exchange_symbol="ZECUSDT", enabled=True)
    candles = await BinanceFuturesClient().fetch_klines(
        symbol,
        "1h",
        700,
        _timestamp("2026-06-15 00:00"),
        _timestamp("2026-07-09 00:00"),
    )
    bars = [candle.to_bar() for candle in candles]
    indexes = {
        name: next(index for index, bar in enumerate(bars) if bar.timestamp == timestamp)
        for name, timestamp in {
            "left_neckline": _timestamp("2026-06-26 16:00"),
            "trendline_p1": _timestamp("2026-07-03 04:00"),
            "trendline_p2": _timestamp("2026-07-06 12:00"),
            "trendline_p3": _timestamp("2026-07-07 04:00"),
        }.items()
    }
    visible = bars[: indexes["trendline_p3"] + 7]
    result = InverseHeadShoulders().detect(visible)
    expected_times = [
        _timestamp("2026-06-25 13:00"),
        _timestamp("2026-06-28 22:00"),
        _timestamp("2026-07-01 01:00"),
    ]
    expected_prices = [386.01, 367.77, 385.07]
    actual_prices = [point[1] for point in result.geometry.get("points", ())]
    assert result.detected
    assert result.metadata["state"] == "breakout_confirmed"
    assert result.geometry["point_timestamps"] == expected_times
    assert all(
        isclose(actual, expected, abs_tol=1e-9)
        for actual, expected in zip(actual_prices, expected_prices)
    )
    assert isclose(result.score, 90.8737, abs_tol=1e-4)
    trendline = ThreePointTrendlineSupport()
    horizontal = HorizontalSupport(swing_detector=trendline.swing_detector)
    anchors = (
        indexes["trendline_p1"],
        indexes["trendline_p2"],
        indexes["trendline_p3"],
    )
    trendline_result = trendline.detect_anchors(visible, anchors)
    horizontal_result = horizontal.detect_at(visible, indexes["trendline_p1"])
    assert trendline_result.detected
    assert trendline_result.geometry["point_timestamps"] == [
        bars[index].timestamp for index in anchors
    ]
    assert trendline_result.metadata["anchor_confirmation_offsets"] == (0, 0, 1)
    assert horizontal_result.detected
    assert horizontal_result.metadata["rule_type"] == "breakout_retest"
    assert horizontal_result.geometry["points"] == [
        (indexes["left_neckline"], 429.25),
        (indexes["trendline_p1"], 425.08),
    ]
    assert indexes["left_neckline"] in {
        point[0] for point in result.geometry["neckline_points"]
    }
    lineage = SupportLineageScore().calculate(
        support_lineage_features(result, horizontal_result, trendline_result)
    )
    assert lineage.metadata["gate_passed"] is True
    assert isclose(lineage.score, 91.7757, abs_tol=1e-4)
    LOGGER.info(
        "ZECUSDT validated: inverse=%s trendline=%s horizontal=%s",
        [_utc_plus_8(value) for value in result.geometry["point_timestamps"]],
        [
            _utc_plus_8(value)
            for value in trendline_result.geometry["point_timestamps"]
        ],
        [
            _utc_plus_8(value)
            for value in horizontal_result.geometry["point_timestamps"]
        ],
    )
    LOGGER.info(
        "scores: inverse=%.4f trendline=%.4f horizontal=%.4f lineage=%.4f",
        result.score,
        trendline_result.score,
        horizontal_result.score,
        lineage.score,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(validate())
