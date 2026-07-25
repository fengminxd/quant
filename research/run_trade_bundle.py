"""Generate three synchronized Price Action research files for one candle range."""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtest.trade_outcome_labels import parse_anchor_trades
from backtest.anchor_outcomes import AnchorTradeOutcomeEvaluator
from data.candles import Candle, timeframe_to_milliseconds
from data.market_config import load_market_data_config, load_supabase_config
from data.supabase_store import SupabaseCandleStore
from research.anchor_trade_report import write_anchor_trade_report
from research.pattern_dedup import select_temporally_distinct_events
from research.pattern_scan import HistoricalPatternScanner, SCAN_TIMEFRAMES, candles_to_bars
from visualization.pattern_pdf import write_symbol_pdf
from visualization.trade_outcome_pdf import write_trade_outcome_pdf


UTC_PLUS_8 = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class TradeBundleResult:
    """Paths and cohort sizes produced by one synchronized generation run."""

    rule_details_pdf: Path
    trade_report_txt: Path
    trade_points_pdf: Path
    candle_count: int
    event_count: int
    trade_count: int


async def generate_trade_bundle(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    output_dir: str | Path | None = None,
    nearby_hours: float = 24.0,
    candles_per_page: int = 168,
    stop_loss_ratio: float = 0.015,
    take_profit_ratio: float = 0.015,
    page_size: int = 1000,
    symbols_config: str | Path = "config/symbols.json",
    supabase_config: str | Path = "config/supabase.json",
    store: SupabaseCandleStore | None = None,
    now_ms: int | None = None,
) -> TradeBundleResult:
    """Generate rule details, trade report, and continuous trade-point PDF."""

    normalized_symbol = symbol.upper()
    _validate_symbol(normalized_symbol, symbols_config)
    start = _require_utc_plus_8(start, "start")
    end = _require_utc_plus_8(end, "end")
    interval_ms = _validate_range(timeframe, start, end, now_ms)
    evaluator = AnchorTradeOutcomeEvaluator(
        stop_loss_ratio=stop_loss_ratio,
        take_profit_ratio=take_profit_ratio,
    )
    database = store or SupabaseCandleStore(load_supabase_config(supabase_config))
    candles = await database.closed_candles(
        normalized_symbol,
        timeframe,
        page_size,
    )
    selected = _select_range(candles, start, end, interval_ms)
    bars = candles_to_bars(selected, timeframe)
    events = HistoricalPatternScanner().scan(normalized_symbol, timeframe, bars)
    events = select_temporally_distinct_events(events, nearby_hours)
    range_name = (
        f"{start.strftime('%Y%m%dT%H%M')}_{end.strftime('%Y%m%dT%H%M')}"
        f"_sl{_ratio_token(stop_loss_ratio)}_tp{_ratio_token(take_profit_ratio)}"
    )
    default_dir = (
        Path("logs")
        / f"{normalized_symbol.lower()}_{timeframe}_trade_bundle"
        / range_name
        / "pdf"
    )
    target_dir = Path(output_dir) if output_dir is not None else default_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{normalized_symbol}_{timeframe}"
    rule_pdf = target_dir / f"{prefix}_规则明细.pdf"
    report_txt = target_dir / f"{prefix}_开单报告.txt"
    points_pdf = target_dir / f"{prefix}_开单点K线总览.pdf"
    write_symbol_pdf(
        normalized_symbol,
        {timeframe: bars},
        events,
        rule_pdf,
        report_notes=(
            f"Stop loss: {stop_loss_ratio:.4%}",
            f"Take profit: {take_profit_ratio:.4%}",
            f"Gross reward/risk: {take_profit_ratio / stop_loss_ratio:.2f}",
        ),
    )
    write_anchor_trade_report(
        events,
        {timeframe: bars},
        report_txt,
        source_pdf=rule_pdf,
        evaluator=evaluator,
    )
    trades = parse_anchor_trades(report_txt, allow_empty=True)
    write_trade_outcome_pdf(
        normalized_symbol,
        timeframe,
        bars,
        trades,
        points_pdf,
        candles_per_page=candles_per_page,
        stop_loss_ratio=stop_loss_ratio,
        take_profit_ratio=take_profit_ratio,
    )
    return TradeBundleResult(
        rule_pdf,
        report_txt,
        points_pdf,
        len(bars),
        len(events),
        len(trades),
    )


def _validate_symbol(symbol: str, config_path: str | Path) -> None:
    enabled = {item.name for item in load_market_data_config(config_path).enabled_symbols}
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
        raise ValueError(
            f"trade bundle timeframe must be one of {supported}; 1d is trend-context only"
        )
    if start > end:
        raise ValueError("start must not be later than end")
    interval_ms = timeframe_to_milliseconds(timeframe)
    start_ms, end_ms = _milliseconds(start), _milliseconds(end)
    if start_ms % interval_ms or end_ms % interval_ms:
        raise ValueError(f"start and end must align to {timeframe} candle open times")
    clock_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    latest_completed = (clock_ms // interval_ms - 1) * interval_ms
    if end_ms > latest_completed:
        latest = _format_utc_plus_8(latest_completed)
        raise ValueError(f"end includes an unclosed candle; latest completed open is {latest}")
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
            f"got {len(selected)}, first missing {_format_utc_plus_8(missing)}"
        )
    return selected


def _require_utc_plus_8(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(hours=8):
        raise ValueError(f"{name} must be timezone-aware UTC+8")
    return value


def _milliseconds(value: datetime) -> int:
    return round(value.timestamp() * 1000)


def _format_utc_plus_8(timestamp_ms: int) -> str:
    value = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return value.astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M UTC+8")


def _ratio_token(value: float) -> str:
    return f"{value * 100:g}".replace(".", "p")


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC_PLUS_8)


def main() -> None:
    """Parse the three required inputs and generate all research files."""

    parser = argparse.ArgumentParser(
        description="Generate rule-details PDF, trade report, and trade-point overview"
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True, choices=SCAN_TIMEFRAMES)
    parser.add_argument("--start", required=True, type=_parse_time, help="UTC+8, inclusive")
    parser.add_argument("--end", required=True, type=_parse_time, help="UTC+8, inclusive")
    parser.add_argument("--stop-loss-pct", type=float, default=1.5)
    parser.add_argument("--take-profit-pct", type=float, default=1.5)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        generate_trade_bundle(
            args.symbol,
            args.timeframe,
            args.start,
            args.end,
            output_dir=args.output_dir,
            stop_loss_ratio=args.stop_loss_pct / 100.0,
            take_profit_ratio=args.take_profit_pct / 100.0,
        )
    )
    print(f"rule_details_pdf={result.rule_details_pdf}")
    print(f"trade_report_txt={result.trade_report_txt}")
    print(f"trade_points_pdf={result.trade_points_pdf}")
    print(
        f"candles={result.candle_count} events={result.event_count} "
        f"trades={result.trade_count}"
    )


if __name__ == "__main__":
    main()
