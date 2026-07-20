from __future__ import annotations

import asyncio
from typing import Any

from data.candles import Candle
from data.supabase_store import SupabaseCandleStore


def record(open_time: int) -> dict[str, Any]:
    return Candle(
        symbol="BTC",
        exchange_symbol="BTCUSDT",
        timeframe="15m",
        open_time=open_time,
        close_time=open_time + 899_999,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=100.0,
    ).to_record()


class FakePagedStore(SupabaseCandleStore):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.cursors: list[str | None] = []

    async def _get(self, params: dict[str, str]) -> list[dict[str, Any]]:
        cursor = params.get("open_time")
        self.cursors.append(cursor)
        lower_bound = int(cursor.removeprefix("gt.")) if cursor else -1
        eligible = [row for row in self.rows if int(row["open_time"]) > lower_bound]
        return eligible[: int(params["limit"])]


def test_closed_candles_pages_by_open_time() -> None:
    store = FakePagedStore([record(index * 900_000) for index in range(5)])

    candles = asyncio.run(store.closed_candles("BTC", "15m", page_size=2))

    assert [candle.open_time for candle in candles] == [
        0,
        900_000,
        1_800_000,
        2_700_000,
        3_600_000,
    ]
    assert store.cursors == [None, "gt.900000", "gt.2700000"]
