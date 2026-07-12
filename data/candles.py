"""OHLCV candle records used by data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models import Bar


@dataclass(frozen=True)
class Candle:
    """Exchange candle with storage metadata."""

    symbol: str
    exchange_symbol: str
    timeframe: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None = None
    trade_count: int | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None
    is_closed: bool = True
    source: str = "binance_usdm_futures"

    def to_bar(self) -> Bar:
        """Convert the candle to the framework Bar type."""

        return Bar(
            timestamp=self.open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            timeframe=self.timeframe,
        )

    def to_record(self) -> dict[str, Any]:
        """Convert the candle to a Supabase row."""

        return {
            "symbol": self.symbol,
            "exchange_symbol": self.exchange_symbol,
            "timeframe": self.timeframe,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "trade_count": self.trade_count,
            "taker_buy_base_volume": self.taker_buy_base_volume,
            "taker_buy_quote_volume": self.taker_buy_quote_volume,
            "is_closed": self.is_closed,
            "source": self.source,
        }


def timeframe_to_milliseconds(timeframe: str) -> int:
    """Return Binance timeframe duration in milliseconds."""

    unit = timeframe[-1]
    value = int(timeframe[:-1])
    multipliers = {
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }
    if unit not in multipliers:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return value * multipliers[unit]
