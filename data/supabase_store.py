"""Supabase REST storage for OHLCV candles."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from data.candles import Candle
from data.market_config import SupabaseConfig


class SupabaseCandleStore:
    """Persist and query candles through Supabase PostgREST."""

    def __init__(self, config: SupabaseConfig) -> None:
        self.config = config
        self.base_url = f"{config.url}/rest/v1/{config.table}"
        self.headers = {
            "apikey": config.service_key,
            "Authorization": f"Bearer {config.service_key}",
            "Content-Type": "application/json",
        }

    async def latest_closed_open_time(
        self,
        symbol: str,
        timeframe: str,
        max_open_time: int,
    ) -> int | None:
        """Return the latest completed candle that is closed by the given time."""

        rows = await self._get(
            {
                "select": "open_time",
                "symbol": f"eq.{symbol}",
                "timeframe": f"eq.{timeframe}",
                "is_closed": "eq.true",
                "open_time": f"lte.{max_open_time}",
                "order": "open_time.desc",
                "limit": "1",
            }
        )
        return int(rows[0]["open_time"]) if rows else None

    async def recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        """Load recent candles ordered from oldest to newest."""

        rows = await self._get(
            {
                "select": "*",
                "symbol": f"eq.{symbol}",
                "timeframe": f"eq.{timeframe}",
                "order": "open_time.desc",
                "limit": str(limit),
            }
        )
        return [self._record_to_candle(row) for row in reversed(rows)]

    async def closed_candles(
        self,
        symbol: str,
        timeframe: str,
        page_size: int = 1000,
    ) -> list[Candle]:
        """Load every closed candle using an open-time cursor."""

        if page_size <= 0:
            raise ValueError("page_size must be positive")
        candles: list[Candle] = []
        last_open_time: int | None = None
        while True:
            params = {
                "select": "*",
                "symbol": f"eq.{symbol}",
                "timeframe": f"eq.{timeframe}",
                "is_closed": "eq.true",
                "order": "open_time.asc",
                "limit": str(page_size),
            }
            if last_open_time is not None:
                params["open_time"] = f"gt.{last_open_time}"
            rows = await self._get(params)
            page = [self._record_to_candle(row) for row in rows]
            candles.extend(page)
            if len(page) < page_size:
                break
            next_open_time = page[-1].open_time
            if next_open_time == last_open_time:
                raise RuntimeError("candle pagination cursor did not advance")
            last_open_time = next_open_time
        return candles

    async def upsert_candles(self, candles: Sequence[Candle]) -> None:
        """Upsert candles by symbol, timeframe, and open_time."""

        if not candles:
            return
        await self._post([candle.to_record() for candle in candles])

    async def _get(self, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to use Supabase storage") from exc

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(self.base_url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

    async def _post(self, payload: list[dict[str, Any]]) -> None:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to use Supabase storage") from exc

        headers = {
            **self.headers,
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        params = {"on_conflict": "symbol,timeframe,open_time"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.base_url, headers=headers, params=params, json=payload)
            response.raise_for_status()

    @staticmethod
    def _record_to_candle(row: dict[str, Any]) -> Candle:
        return Candle(
            symbol=str(row["symbol"]),
            exchange_symbol=str(row["exchange_symbol"]),
            timeframe=str(row["timeframe"]),
            open_time=int(row["open_time"]),
            close_time=int(row["close_time"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            quote_volume=_optional_float(row.get("quote_volume")),
            trade_count=_optional_int(row.get("trade_count")),
            taker_buy_base_volume=_optional_float(row.get("taker_buy_base_volume")),
            taker_buy_quote_volume=_optional_float(row.get("taker_buy_quote_volume")),
            is_closed=bool(row["is_closed"]),
            source=str(row.get("source", "binance_usdm_futures")),
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
