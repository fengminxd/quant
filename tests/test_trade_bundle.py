from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from data.candles import Candle
from research.run_trade_bundle import generate_trade_bundle


UTC_PLUS_8 = timezone(timedelta(hours=8))


class FakeStore:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles

    async def closed_candles(
        self,
        symbol: str,
        timeframe: str,
        page_size: int,
    ) -> list[Candle]:
        assert (symbol, timeframe, page_size) == ("BTC", "1h", 1000)
        return self.candles


def make_candles(start: datetime, count: int) -> list[Candle]:
    start_ms = round(start.timestamp() * 1000)
    return [
        Candle(
            symbol="BTC",
            exchange_symbol="BTCUSDT",
            timeframe="1h",
            open_time=start_ms + index * 3_600_000,
            close_time=start_ms + (index + 1) * 3_600_000 - 1,
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1000.0,
        )
        for index in range(count)
    ]


def test_generate_trade_bundle_writes_three_synchronized_files(tmp_path) -> None:
    start = datetime(2026, 7, 1, 8, tzinfo=UTC_PLUS_8)
    candles = make_candles(start, 41)
    end = start + timedelta(hours=40)

    result = asyncio.run(
        generate_trade_bundle(
            "btc",
            "1h",
            start,
            end,
            output_dir=tmp_path,
            store=FakeStore(candles),
            now_ms=round((end + timedelta(hours=2)).timestamp() * 1000),
            stop_loss_ratio=0.01,
            take_profit_ratio=0.03,
        )
    )

    assert result.candle_count == 41
    assert result.event_count == 0
    assert result.trade_count == 0
    assert result.rule_details_pdf.name == "BTC_1h_规则明细.pdf"
    assert result.trade_report_txt.name == "BTC_1h_开单报告.txt"
    assert result.trade_points_pdf.name == "BTC_1h_开单点K线总览.pdf"
    report = result.trade_report_txt.read_text(encoding="utf-8")
    assert "止损比例 1.0000%" in report
    assert "止盈比例 3.0000%" in report
    assert "Gross R:R 3.00" in report
    assert all(
        path.is_file()
        for path in (
            result.rule_details_pdf,
            result.trade_report_txt,
            result.trade_points_pdf,
        )
    )


def test_trade_bundle_rejects_daily_trade_generation(tmp_path) -> None:
    start = datetime(2026, 7, 1, 8, tzinfo=UTC_PLUS_8)

    with pytest.raises(ValueError, match="1d is trend-context only"):
        asyncio.run(
            generate_trade_bundle(
                "BTC",
                "1d",
                start,
                start,
                output_dir=tmp_path,
                store=FakeStore([]),
            )
        )
