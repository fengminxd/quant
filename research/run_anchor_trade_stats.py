"""Generate anchor-entry outcome text from database history without a PDF redraw."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from data.market_config import load_market_data_config, load_supabase_config
from data.supabase_store import SupabaseCandleStore
from research.anchor_trade_report import write_anchor_trade_report
from research.pattern_dedup import select_temporally_distinct_events
from research.pattern_scan import (
    SCAN_TIMEFRAMES,
    HistoricalPatternScanner,
    candles_to_bars,
)

LOGGER = logging.getLogger(__name__)


async def run_anchor_trade_stats(
    symbol: str,
    timeframe: str,
    output_path: str | Path,
    *,
    source_pdf: str | Path,
    symbols_config: str = "config/symbols.json",
    supabase_config: str = "config/supabase.json",
    page_size: int = 1000,
    nearby_hours: float = 24.0,
) -> Path:
    """Scan the same cohort as the PDF and write only its outcome text."""

    if timeframe not in SCAN_TIMEFRAMES:
        raise ValueError(f"unsupported scan timeframe: {timeframe}")
    market = load_market_data_config(symbols_config)
    enabled = {item.name for item in market.enabled_symbols}
    if symbol not in enabled:
        raise ValueError(f"symbol is not enabled: {symbol}")
    store = SupabaseCandleStore(load_supabase_config(supabase_config))
    candles = await store.closed_candles(symbol, timeframe, page_size)
    bars = candles_to_bars(candles, timeframe)
    found = HistoricalPatternScanner().scan(symbol, timeframe, bars)
    events = select_temporally_distinct_events(found, nearby_hours)
    target = write_anchor_trade_report(
        events,
        {timeframe: bars},
        output_path,
        source_pdf=source_pdf,
    )
    LOGGER.info(
        "wrote %s from %s %s events=%s",
        target,
        symbol,
        timeframe,
        len(events),
    )
    return target


def main() -> None:
    """Parse CLI arguments and generate one text-only result report."""

    parser = argparse.ArgumentParser(
        description="Write retrospective ±1.5% Pattern anchor outcomes"
    )
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--timeframe", choices=SCAN_TIMEFRAMES, default="1h")
    parser.add_argument(
        "--output",
        default=(
            "logs/btc_1h_pdf_explanations/pdf/"
            "BTC_1h_anchor_trade_outcomes.txt"
        ),
    )
    parser.add_argument(
        "--source-pdf",
        default="logs/btc_1h_pdf_explanations/pdf/BTC.pdf",
    )
    parser.add_argument("--symbols-config", default="config/symbols.json")
    parser.add_argument("--supabase-config", default="config/supabase.json")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--nearby-hours", type=float, default=24.0)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(
        run_anchor_trade_stats(
            args.symbol.upper(),
            args.timeframe,
            args.output,
            source_pdf=args.source_pdf,
            symbols_config=args.symbols_config,
            supabase_config=args.supabase_config,
            page_size=args.page_size,
            nearby_hours=args.nearby_hours,
        )
    )


if __name__ == "__main__":
    main()
