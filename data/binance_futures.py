"""Binance USD-M futures market data client."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

from data.candles import Candle
from data.market_config import SymbolConfig

LOGGER = logging.getLogger(__name__)
SUPPORTED_CONTRACT_TYPES = {"PERPETUAL", "TRADIFI_PERPETUAL"}


class BinanceFuturesClient:
    """REST and WebSocket client for Binance USD-M futures klines."""

    def __init__(
        self,
        rest_base_url: str = "https://fapi.binance.com",
        ws_base_url: str = "wss://fstream.binance.com/stream",
    ) -> None:
        self.rest_base_url = rest_base_url.rstrip("/")
        self.ws_base_url = ws_base_url

    async def filter_usdt_perpetual_symbols(
        self,
        symbols: tuple[SymbolConfig, ...],
    ) -> tuple[SymbolConfig, ...]:
        """Keep symbols listed as trading USDT-margined perpetual contracts."""

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to validate Binance futures symbols") from exc

        async with httpx.AsyncClient(base_url=self.rest_base_url, timeout=20.0) as client:
            response = await client.get("/fapi/v1/exchangeInfo")
            response.raise_for_status()
            payload = response.json()

        allowed = {
            str(item["symbol"]).upper()
            for item in payload.get("symbols", [])
            if item.get("contractType") in SUPPORTED_CONTRACT_TYPES
            and item.get("quoteAsset") == "USDT"
            and item.get("marginAsset") == "USDT"
            and item.get("status") == "TRADING"
        }
        valid: list[SymbolConfig] = []
        for symbol in symbols:
            if symbol.exchange_symbol in allowed:
                valid.append(symbol)
            else:
                LOGGER.warning(
                    "skipping %s: not a supported trading USDT-margined perpetual contract",
                    symbol.exchange_symbol,
                )
        return tuple(valid)

    async def fetch_klines(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        limit: int,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        """Fetch futures klines, paginating when a start time is supplied."""

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to fetch Binance futures klines") from exc

        if start_time is None and limit > 1500:
            return await self._fetch_recent_klines(symbol, timeframe, limit, end_time)

        rows: list[list[Any]] = []
        next_start = start_time
        async with httpx.AsyncClient(base_url=self.rest_base_url, timeout=20.0) as client:
            while len(rows) < limit:
                request_limit = min(1500, limit - len(rows))
                params: dict[str, Any] = {
                    "symbol": symbol.exchange_symbol,
                    "interval": timeframe,
                    "limit": request_limit,
                }
                if next_start is not None:
                    params["startTime"] = next_start
                if end_time is not None:
                    params["endTime"] = end_time
                response = await client.get("/fapi/v1/klines", params=params)
                response.raise_for_status()
                batch = response.json()
                if not batch:
                    break
                rows.extend(batch)
                if start_time is None or len(batch) < request_limit:
                    break
                next_start = int(batch[-1][0]) + 1
        return [self._row_to_candle(symbol, timeframe, row, is_closed=True) for row in rows[:limit]]

    async def _fetch_recent_klines(
        self,
        symbol: SymbolConfig,
        timeframe: str,
        limit: int,
        end_time: int | None,
    ) -> list[Candle]:
        """Fetch the most recent candles by paging backward from end_time."""

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to fetch Binance futures klines") from exc

        rows: list[list[Any]] = []
        next_end = end_time
        async with httpx.AsyncClient(base_url=self.rest_base_url, timeout=20.0) as client:
            while len(rows) < limit:
                request_limit = min(1500, limit - len(rows))
                params: dict[str, Any] = {
                    "symbol": symbol.exchange_symbol,
                    "interval": timeframe,
                    "limit": request_limit,
                }
                if next_end is not None:
                    params["endTime"] = next_end
                response = await client.get("/fapi/v1/klines", params=params)
                response.raise_for_status()
                batch = response.json()
                if not batch:
                    break
                rows = batch + rows
                if len(batch) < request_limit:
                    break
                next_end = int(batch[0][0]) - 1
        ordered = sorted(rows, key=lambda row: int(row[0]))
        recent = ordered[-limit:]
        return [self._row_to_candle(symbol, timeframe, row, is_closed=True) for row in recent]

    async def stream_klines(
        self,
        symbols: tuple[SymbolConfig, ...],
        timeframes: tuple[str, ...],
    ) -> AsyncIterator[Candle]:
        """Yield live kline updates from Binance combined streams."""

        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("install websockets to stream Binance futures klines") from exc

        stream_names = [
            f"{symbol.exchange_symbol.lower()}@kline_{timeframe}"
            for symbol in symbols
            for timeframe in timeframes
        ]
        symbol_by_exchange = {symbol.exchange_symbol: symbol for symbol in symbols}
        url = f"{self.ws_base_url}?{urlencode({'streams': '/'.join(stream_names)})}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                    async for message in websocket:
                        payload = json.loads(message)
                        candle = self._payload_to_candle(payload, symbol_by_exchange)
                        if candle is not None:
                            yield candle
            except Exception:
                LOGGER.exception("Binance websocket disconnected; reconnecting")
                await asyncio.sleep(5)

    @staticmethod
    def current_time_ms() -> int:
        """Return current UTC timestamp in milliseconds."""

        return int(time.time() * 1000)

    @staticmethod
    def _row_to_candle(
        symbol: SymbolConfig,
        timeframe: str,
        row: list[Any],
        is_closed: bool,
    ) -> Candle:
        return Candle(
            symbol=symbol.name,
            exchange_symbol=symbol.exchange_symbol,
            timeframe=timeframe,
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=int(row[6]),
            quote_volume=float(row[7]),
            trade_count=int(row[8]),
            taker_buy_base_volume=float(row[9]),
            taker_buy_quote_volume=float(row[10]),
            is_closed=is_closed,
        )

    @staticmethod
    def _payload_to_candle(
        payload: dict[str, Any],
        symbol_by_exchange: dict[str, SymbolConfig],
    ) -> Candle | None:
        event = payload.get("data", {})
        kline = event.get("k", {})
        exchange_symbol = str(kline.get("s", "")).upper()
        symbol = symbol_by_exchange.get(exchange_symbol)
        if symbol is None:
            return None
        return Candle(
            symbol=symbol.name,
            exchange_symbol=symbol.exchange_symbol,
            timeframe=str(kline["i"]),
            open_time=int(kline["t"]),
            close_time=int(kline["T"]),
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
            volume=float(kline["v"]),
            quote_volume=float(kline["q"]),
            trade_count=int(kline["n"]),
            taker_buy_base_volume=float(kline["V"]),
            taker_buy_quote_volume=float(kline["Q"]),
            is_closed=bool(kline["x"]),
        )
