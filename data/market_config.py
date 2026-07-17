"""Configuration loading for market data collection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.timeframes import TRADING_TIMEFRAMES, TREND_TIMEFRAMES


DEFAULT_SYMBOL_CONFIG = Path("config/symbols.json")
DEFAULT_SUPABASE_CONFIG = Path("config/supabase.json")


@dataclass(frozen=True)
class SymbolConfig:
    """Tradable symbol and its Binance futures market mapping."""

    name: str
    exchange_symbol: str
    enabled: bool = True


@dataclass(frozen=True)
class MarketDataConfig:
    """Runtime market data configuration."""

    symbols: tuple[SymbolConfig, ...]
    timeframes: tuple[str, ...]
    history_limit: int

    @property
    def enabled_symbols(self) -> tuple[SymbolConfig, ...]:
        """Return enabled symbols only."""

        return tuple(symbol for symbol in self.symbols if symbol.enabled)

    @property
    def trading_timeframes(self) -> tuple[str, ...]:
        """Return configured levels allowed to produce trading structures."""

        return tuple(value for value in self.timeframes if value in TRADING_TIMEFRAMES)

    @property
    def trend_timeframes(self) -> tuple[str, ...]:
        """Return configured trend-context-only levels."""

        return tuple(value for value in self.timeframes if value in TREND_TIMEFRAMES)


@dataclass(frozen=True)
class SupabaseConfig:
    """Supabase REST API and PostgreSQL configuration."""

    url: str
    service_key: str
    table: str
    db_url: str | None = None


def load_market_data_config(path: str | Path = DEFAULT_SYMBOL_CONFIG) -> MarketDataConfig:
    """Load symbol, timeframe, and history settings from JSON."""

    payload = _load_json(path)
    default_quote = str(payload.get("default_quote_asset", "USDT")).upper()
    symbols = tuple(_parse_symbol(item, default_quote) for item in payload["symbols"])
    timeframes = tuple(
        str(value)
        for value in payload.get("timeframes", ["15m", "1h", "4h", "1d"])
    )
    history_limit = int(payload.get("history_limit", 2000))
    return MarketDataConfig(symbols=symbols, timeframes=timeframes, history_limit=history_limit)


def load_supabase_config(path: str | Path = DEFAULT_SUPABASE_CONFIG) -> SupabaseConfig:
    """Load Supabase settings, resolving secret values from environment names."""

    payload = _load_json(path)
    url = _resolve_config_value(payload, "url", "url_env")
    key = _resolve_config_value(payload, "service_key", "service_key_env")
    db_url = _resolve_config_value(payload, "db_url", "db_url_env") or None
    table = str(payload.get("table", "ohlcv_candles"))
    if not url or not key:
        raise ValueError("Supabase url/key are required through config values or environment variables")
    return SupabaseConfig(url=url.rstrip("/"), service_key=key, table=table, db_url=db_url)


def _parse_symbol(item: dict[str, Any], default_quote: str) -> SymbolConfig:
    name = str(item["name"]).upper()
    exchange_symbol = str(item.get("exchange_symbol") or f"{name}{default_quote}").upper()
    enabled = bool(item.get("enabled", True))
    return SymbolConfig(name=name, exchange_symbol=exchange_symbol, enabled=enabled)


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_config_value(payload: dict[str, Any], value_key: str, env_key: str) -> str:
    """Resolve a literal config value or an environment variable reference."""

    if payload.get(value_key):
        return str(payload[value_key])
    env_or_value = str(payload.get(env_key, ""))
    if not env_or_value:
        return ""
    return os.environ.get(env_or_value, env_or_value)
