"""Command line entry point for database-backed historical Pattern reports."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Sequence

from core.models import Bar
from data.market_config import load_market_data_config, load_supabase_config
from data.supabase_store import SupabaseCandleStore
from research.pattern_dedup import select_temporally_distinct_events
from research.pattern_scan import (
    SCAN_TIMEFRAMES,
    HistoricalPatternScanner,
    candles_to_bars,
    event_log_line,
)
from visualization.pattern_pdf import write_symbol_pdf


LOGGER = logging.getLogger(__name__)


async def run_scan(
    symbols_config: str,
    supabase_config: str,
    output_dir: str | Path,
    selected_symbols: set[str] | None = None,
    page_size: int = 1000,
    workers: int | None = None,
    nearby_hours: float = 24.0,
    timeframes: Sequence[str] = SCAN_TIMEFRAMES,
) -> dict[str, int]:
    """Scan configured symbols and return detected event counts by symbol."""

    market = load_market_data_config(symbols_config)
    store = SupabaseCandleStore(load_supabase_config(supabase_config))
    target_timeframes = tuple(timeframes)
    if not target_timeframes or any(value not in SCAN_TIMEFRAMES for value in target_timeframes):
        raise ValueError(f"timeframes must be a non-empty subset of {SCAN_TIMEFRAMES}")
    target_dir = Path(output_dir)
    pdf_dir = target_dir / "pdf"
    target_dir.mkdir(parents=True, exist_ok=True)
    symbols = [
        symbol
        for symbol in market.enabled_symbols
        if selected_symbols is None or symbol.name in selected_symbols
    ]
    counts: dict[str, int] = {}
    log_path = target_dir / "pattern_scan.log"
    worker_count = workers or max(1, min(2, os.cpu_count() or 1))
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        pending = []
        for symbol in symbols:
            LOGGER.info("loading %s %s", symbol.name, ",".join(target_timeframes))
            candle_groups = await asyncio.gather(
                *(
                    store.closed_candles(symbol.name, timeframe, page_size)
                    for timeframe in target_timeframes
                )
            )
            bars_by_timeframe = {
                timeframe: candles_to_bars(candles, timeframe)
                for timeframe, candles in zip(target_timeframes, candle_groups)
            }
            pending.append(
                loop.run_in_executor(
                    executor,
                    _scan_symbol,
                    symbol.name,
                    bars_by_timeframe,
                    pdf_dir / f"{symbol.name}.pdf",
                    nearby_hours,
                    target_timeframes,
                )
            )
        with log_path.open("w", encoding="utf-8") as log_file:
            for future in asyncio.as_completed(pending):
                symbol_name, timeframe_counts, lines = await future
                counts[symbol_name] = sum(timeframe_counts.values())
                log_file.write("\n".join(lines) + ("\n" if lines else ""))
                log_file.flush()
                LOGGER.info(
                    "wrote %s with counts=%s",
                    pdf_dir / f"{symbol_name}.pdf",
                    timeframe_counts,
                )
    return counts


def _scan_symbol(
    symbol: str,
    bars_by_timeframe: dict[str, Sequence[Bar]],
    pdf_path: Path,
    nearby_hours: float,
    timeframes: Sequence[str],
) -> tuple[str, dict[str, int], list[str]]:
    """Scan and render one symbol inside a worker process."""

    scanner = HistoricalPatternScanner()
    events = []
    timeframe_counts = {}
    for timeframe in timeframes:
        found = scanner.scan(symbol, timeframe, bars_by_timeframe[timeframe])
        events.extend(found)
        timeframe_counts[timeframe] = len(found)
    events = select_temporally_distinct_events(events, nearby_hours)
    timeframe_counts = {
        timeframe: sum(event.timeframe == timeframe for event in events)
        for timeframe in timeframes
    }
    write_symbol_pdf(symbol, bars_by_timeframe, events, pdf_path)
    return symbol, timeframe_counts, [event_log_line(event) for event in events]


def main() -> None:
    """Parse CLI arguments and run the historical Pattern scan."""

    parser = argparse.ArgumentParser(description="Scan PATTERN_002-008 and write per-symbol PDFs")
    parser.add_argument("--symbols-config", default="config/symbols.json")
    parser.add_argument("--supabase-config", default="config/supabase.json")
    parser.add_argument("--output-dir", default="logs/pattern_scan")
    parser.add_argument("--symbols", nargs="*", help="Optional configured symbol names")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--workers", type=int, help="Parallel symbol report workers")
    parser.add_argument("--nearby-hours", type=float, default=24.0)
    parser.add_argument("--timeframes", nargs="+", choices=SCAN_TIMEFRAMES, default=SCAN_TIMEFRAMES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    selected = {value.upper() for value in args.symbols} if args.symbols else None
    counts = asyncio.run(
        run_scan(
            args.symbols_config,
            args.supabase_config,
            args.output_dir,
            selected,
            args.page_size,
            args.workers,
            args.nearby_hours,
            args.timeframes,
        )
    )
    LOGGER.info("scan complete: %s", counts)


if __name__ == "__main__":
    main()
