"""Generate an independent aggressive trade report from historical candles."""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtest.aggressive_anchor_strategy import AggressiveAnchorStrategyEvaluator
from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import load_market_data_config, load_supabase_config
from data.supabase_store import SupabaseCandleStore
from features.trade_feasibility import TransactionCostModel
from research.aggressive_pattern_scan import AggressivePatternScanner
from research.aggressive_trade_report import write_aggressive_trade_report
from research.pattern_dedup import select_temporally_distinct_events
from research.pattern_scan import SCAN_TIMEFRAMES, candles_to_bars

UTC_PLUS_8 = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class AggressiveReportResult:
    """Generated report path and independently scanned cohort sizes."""

    report_path: Path
    candle_count: int
    event_count: int
    trade_count: int


async def generate_aggressive_trade_report(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    output_dir: str | Path | None = None,
    nearby_hours: float = 24.0,
    stop_loss_ratio: float = 0.015,
    lock_trigger_ratio: float = 0.015,
    take_profit_ratio: float = 0.03,
    entry_fee_rate: float = 0.0002,
    exit_fee_rate: float = 0.0005,
    page_size: int = 1000,
    symbols_config: str | Path = "config/symbols.json",
    supabase_config: str | Path = "config/supabase.json",
    store: SupabaseCandleStore | None = None,
    now_ms: int | None = None,
) -> AggressiveReportResult:
    """Scan closed candles and write the standalone aggressive strategy report."""

    normalized_symbol = symbol.upper()
    _validate_symbol(normalized_symbol, symbols_config)
    start = _require_utc_plus_8(start, "start")
    end = _require_utc_plus_8(end, "end")
    interval_ms = _validate_range(timeframe, start, end, now_ms)
    database = store or SupabaseCandleStore(load_supabase_config(supabase_config))
    candles = await database.closed_candles(
        normalized_symbol,
        timeframe,
        page_size,
    )
    selected = _select_range(candles, start, end, interval_ms)
    bars = candles_to_bars(selected, timeframe)
    events = AggressivePatternScanner().scan(normalized_symbol, timeframe, bars)
    events = select_temporally_distinct_events(events, nearby_hours)
    evaluator = AggressiveAnchorStrategyEvaluator(
        stop_loss_ratio=stop_loss_ratio,
        lock_trigger_ratio=lock_trigger_ratio,
        take_profit_ratio=take_profit_ratio,
        costs=TransactionCostModel(
            entry_fee_rate=entry_fee_rate,
            exit_fee_rate=exit_fee_rate,
        ),
    )
    target_dir = (
        Path(output_dir)
        if output_dir is not None
        else Path("logs")
        / f"{normalized_symbol.lower()}_{timeframe}_aggressive_trade_report"
        / (
            f"{start.strftime('%Y%m%dT%H%M')}_{end.strftime('%Y%m%dT%H%M')}"
            f"_sl{_ratio_token(stop_loss_ratio)}"
            f"_lock{_ratio_token(lock_trigger_ratio)}"
            f"_tp{_ratio_token(take_profit_ratio)}"
        )
    )
    report_path = target_dir / f"{normalized_symbol}_{timeframe}_激进开单报告.txt"
    write_aggressive_trade_report(
        events,
        {timeframe: bars},
        report_path,
        start=start,
        end=end,
        evaluator=evaluator,
    )
    trade_count = sum(evaluator.plan(event, bars) is not None for event in events)
    return AggressiveReportResult(
        report_path,
        len(bars),
        len(events),
        trade_count,
    )


def _validate_symbol(symbol: str, config_path: str | Path) -> None:
    enabled = {
        item.name
        for item in load_market_data_config(config_path).enabled_symbols
    }
    if symbol not in enabled:
        raise ValueError(f"symbol is not enabled: {symbol}")


def _validate_range(
    timeframe: str,
    start: datetime,
    end: datetime,
    now_ms: int | None,
) -> int:
    if timeframe not in SCAN_TIMEFRAMES:
        supported = ", ".join(SCAN_TIMEFRAMES)
        raise ValueError(f"aggressive report timeframe must be one of {supported}")
    if start > end:
        raise ValueError("start must not be later than end")
    interval_ms = timeframe_to_milliseconds(timeframe)
    start_ms, end_ms = _milliseconds(start), _milliseconds(end)
    if start_ms % interval_ms or end_ms % interval_ms:
        raise ValueError(f"start and end must align to {timeframe} candle open times")
    clock_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    latest_completed = (clock_ms // interval_ms - 1) * interval_ms
    if end_ms > latest_completed:
        latest = _format_time(latest_completed)
        raise ValueError(
            f"end includes an unclosed candle; latest completed open is {latest}"
        )
    return interval_ms


def _select_range(
    candles: list[Candle],
    start: datetime,
    end: datetime,
    interval_ms: int,
) -> list[Candle]:
    start_ms, end_ms = _milliseconds(start), _milliseconds(end)
    selected = [
        candle for candle in candles if start_ms <= candle.open_time <= end_ms
    ]
    expected = (end_ms - start_ms) // interval_ms + 1
    if len(selected) != expected:
        actual = {candle.open_time for candle in selected}
        missing = next(
            value
            for value in range(start_ms, end_ms + interval_ms, interval_ms)
            if value not in actual
        )
        raise ValueError(
            f"database candle range is incomplete: expected {expected}, "
            f"got {len(selected)}, first missing {_format_time(missing)}"
        )
    return selected


def _require_utc_plus_8(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(hours=8):
        raise ValueError(f"{name} must be timezone-aware UTC+8")
    return value


def _milliseconds(value: datetime) -> int:
    return round(value.timestamp() * 1000)


def _format_time(timestamp_ms: int) -> str:
    value = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return value.astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M UTC+8")


def _ratio_token(value: float) -> str:
    return f"{value * 100:g}".replace(".", "p")


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)


def main() -> None:
    """Parse CLI options and generate one aggressive report."""

    parser = argparse.ArgumentParser(
        description="Generate an independent confirmed-pivot limit-entry report"
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True, choices=SCAN_TIMEFRAMES)
    parser.add_argument("--start", required=True, type=_parse_time, help="UTC+8")
    parser.add_argument("--end", required=True, type=_parse_time, help="UTC+8")
    parser.add_argument("--stop-loss-pct", type=float, default=1.5)
    parser.add_argument("--lock-trigger-pct", type=float, default=1.5)
    parser.add_argument("--take-profit-pct", type=float, default=3.0)
    parser.add_argument("--entry-fee-pct", type=float, default=0.02)
    parser.add_argument("--exit-fee-pct", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        generate_aggressive_trade_report(
            args.symbol,
            args.timeframe,
            args.start,
            args.end,
            output_dir=args.output_dir,
            stop_loss_ratio=args.stop_loss_pct / 100.0,
            lock_trigger_ratio=args.lock_trigger_pct / 100.0,
            take_profit_ratio=args.take_profit_pct / 100.0,
            entry_fee_rate=args.entry_fee_pct / 100.0,
            exit_fee_rate=args.exit_fee_pct / 100.0,
        )
    )
    print(f"aggressive_trade_report={result.report_path}")
    print(
        f"candles={result.candle_count} events={result.event_count} "
        f"trades={result.trade_count}"
    )


if __name__ == "__main__":
    main()
