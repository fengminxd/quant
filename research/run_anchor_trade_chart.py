"""Generate the fixed-snapshot BTC 1h anchor-trade candlestick PDF."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.market_config import load_supabase_config
from data.supabase_store import SupabaseCandleStore
from backtest.trade_outcome_labels import parse_anchor_trades
from features.trade_feasibility import TransactionCostModel
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
    stop_loss_ratio: float = 0.015,
    lock_trigger_ratio: float = 0.015,
    take_profit_ratio: float = 0.03,
    entry_fee_rate: float = 0.0002,
    exit_fee_rate: float = 0.0005,
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
    return write_trade_outcome_pdf(
        "BTC",
        "1h",
        bars,
        trades,
        output_path,
        stop_loss_ratio=stop_loss_ratio,
        lock_trigger_ratio=lock_trigger_ratio,
        take_profit_ratio=take_profit_ratio,
        costs=TransactionCostModel(
            entry_fee_rate=entry_fee_rate,
            exit_fee_rate=exit_fee_rate,
        ),
    )


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
    parser.add_argument(
        "--stop-loss-pct",
        type=float,
        default=1.5,
    )
    parser.add_argument(
        "--lock-profit-pct",
        type=float,
        default=1.5,
    )
    parser.add_argument(
        "--take-profit-pct",
        type=float,
        default=3.0,
    )
    parser.add_argument(
        "--entry-fee-pct",
        "--open-fee-pct",
        dest="entry_fee_pct",
        type=float,
        default=0.02,
    )
    parser.add_argument(
        "--exit-fee-pct",
        "--close-fee-pct",
        dest="exit_fee_pct",
        type=float,
        default=0.05,
    )
    args = parser.parse_args()
    target = asyncio.run(
        run(
            args.report,
            args.output,
            start=args.start,
            end=args.end,
            stop_loss_ratio=args.stop_loss_pct / 100.0,
            lock_trigger_ratio=args.lock_profit_pct / 100.0,
            take_profit_ratio=args.take_profit_pct / 100.0,
            entry_fee_rate=args.entry_fee_pct / 100.0,
            exit_fee_rate=args.exit_fee_pct / 100.0,
        )
    )
    print(target)


if __name__ == "__main__":
    main()
