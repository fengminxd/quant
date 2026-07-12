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

    async def latest_open_time(self, symbol: str, timeframe: str) -> int | None:
        """Return the latest stored open_time for a symbol/timeframe."""

        rows = await self._get(
            {
                "select": "open_time",
                "symbol": f"eq.{symbol}",
                "timeframe": f"eq.{timeframe}",
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
