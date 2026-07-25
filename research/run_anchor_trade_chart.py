"""Generate the fixed-snapshot BTC 1h anchor-trade candlestick PDF."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.market_config import load_supabase_config
from data.supabase_store import SupabaseCandleStore
from backtest.trade_outcome_labels import parse_anchor_trades
from research.pattern_scan import candles_to_bars
from visualization.trade_outcome_pdf import write_trade_outcome_pdf


UTC_PLUS_8 = timezone(timedelta(hours=8))
DEFAULT_REPORT = Path(
    "logs/btc_1h_pdf_explanations/pdf/BTC_1h_anchor_trade_outcomes.txt"
)
DEFAULT_OUTPUT = Path(
    "logs/btc_1h_pdf_explanations/pdf/BTC_1h_anchor_trade_points.pdf"
)


async def run(
    report_path: str | Path,
    output_path: str | Path,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 1000,
) -> Path:
    """Load the source snapshot, validate it, and render its trade actions."""

    candles = await SupabaseCandleStore(
        load_supabase_config()
    ).closed_candles("BTC", "1h", page_size)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    bars = [
        bar
        for bar in candles_to_bars(candles, "1h")
        if start_ms <= bar.timestamp <= end_ms
    ]
    expected_count = int((end - start).total_seconds() // 3600) + 1
    if len(bars) != expected_count:
        raise ValueError(
            f"snapshot requires {expected_count} continuous candles, got {len(bars)}"
        )
    trades = parse_anchor_trades(report_path)
    return write_trade_outcome_pdf("BTC", "1h", bars, trades, output_path)


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)


def main() -> None:
    """Parse arguments and create the PDF."""

    parser = argparse.ArgumentParser(
        description="Draw continuous BTC 1h candles with anchor trade actions"
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--start",
        type=_parse_time,
        default=_parse_time("2026-04-15 12:00"),
        help="Snapshot start in UTC+8",
    )
    parser.add_argument(
        "--end",
        type=_parse_time,
        default=_parse_time("2026-07-20 12:00"),
        help="Snapshot end in UTC+8",
    )
    args = parser.parse_args()
    target = asyncio.run(
        run(args.report, args.output, start=args.start, end=args.end)
    )
    print(target)


if __name__ == "__main__":
    main()
