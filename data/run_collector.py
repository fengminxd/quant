"""Command line entry point for Binance futures candle collection."""

from __future__ import annotations

import argparse
import asyncio
import logging

from data.binance_futures import BinanceFuturesClient
from data.candle_cache import CandleCache
from data.market_config import load_market_data_config, load_supabase_config
from data.market_data_service import MarketDataService
from data.supabase_schema import create_schema
from data.supabase_store import SupabaseCandleStore


def main() -> None:
    """Run the market data collector."""

    parser = argparse.ArgumentParser(description="Sync Binance futures klines to Supabase")
    parser.add_argument("--symbols-config", default="config/symbols.json")
    parser.add_argument("--supabase-config", default="config/supabase.json")
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--bootstrap-only", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    market_config = load_market_data_config(args.symbols_config)
    supabase_config = load_supabase_config(args.supabase_config)
    if args.create_schema:
        create_schema(supabase_config)
        logging.info("Supabase schema is ready")
    service = MarketDataService(
        config=market_config,
        exchange=BinanceFuturesClient(),
        store=SupabaseCandleStore(supabase_config),
        cache=CandleCache(maxlen=market_config.history_limit),
    )
    if args.bootstrap_only:
        asyncio.run(service.bootstrap_history())
    else:
        asyncio.run(service.run_forever())


if __name__ == "__main__":
    main()
