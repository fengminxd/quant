"""Continuous candlestick PDF annotated with anchor-trade actions."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D

from backtest.trade_outcome_labels import AnchorTrade, timestamp_to_utc_plus_8
from core.models import Bar
from data.candles import timeframe_to_milliseconds
from features.trade_feasibility import TransactionCostModel
from visualization.pattern_pdf import _draw_candles
from visualization.trade_annotations import draw_page_trades, write_trade_ledger




def write_trade_outcome_pdf(
    symbol: str,
    timeframe: str,
    bars: Sequence[Bar],
    trades: Sequence[AnchorTrade],
    output_path: str | Path,
    *,
    candles_per_page: int = 168,
    stop_loss_ratio: float = 0.015,
    lock_trigger_ratio: float = 0.015,
    take_profit_ratio: float = 0.03,
    costs: TransactionCostModel | None = None,
) -> Path:
    """Write a summary plus adjacent, non-overlapping candlestick pages."""

    if candles_per_page <= 0:
        raise ValueError("candles_per_page must be positive")
    if not 0.0 < stop_loss_ratio < 1.0:
        raise ValueError("stop_loss_ratio must be between zero and one")
    if not 0.0 < take_profit_ratio < 1.0:
        raise ValueError("take_profit_ratio must be between zero and one")
    if not 0.0 < lock_trigger_ratio < take_profit_ratio:
        raise ValueError("lock_trigger_ratio must be below take_profit_ratio")
    cost_model = costs or TransactionCostModel()
    _validate_continuous_bars(bars)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    page_count = (len(bars) + candles_per_page - 1) // candles_per_page
    metadata = {
        "Title": f"{symbol} {timeframe} Anchor Trade Entries and Exits (UTC+8)",
        "Subject": "Continuous 1h candlesticks with retrospective anchor trades",
        "Author": "Price Action Quant Framework",
    }
    with PdfPages(target, metadata=metadata) as pdf:
        _write_summary(
            pdf,
            symbol,
            timeframe,
            bars,
            trades,
            page_count,
            candles_per_page,
            stop_loss_ratio,
            lock_trigger_ratio,
            take_profit_ratio,
            cost_model,
        )
        for page_number, start in enumerate(
            range(0, len(bars), candles_per_page), start=1
        ):
            _write_chart_page(
                pdf,
                bars[start : start + candles_per_page],
                trades,
                symbol,
                timeframe,
                page_number,
                page_count,
            )
    return target


def _write_summary(
    pdf: PdfPages,
    symbol: str,
    timeframe: str,
    bars: Sequence[Bar],
    trades: Sequence[AnchorTrade],
    page_count: int,
    candles_per_page: int,
    stop_loss_ratio: float,
    lock_trigger_ratio: float,
    take_profit_ratio: float,
    costs: TransactionCostModel,
) -> None:
    figure, axis = plt.subplots(figsize=(11.69, 8.27))
    axis.axis("off")
    outcomes = Counter(trade.outcome for trade in trades)
    directions = Counter(trade.direction for trade in trades)
    page_hours = candles_per_page * timeframe_to_milliseconds(timeframe) / 3_600_000
    lines = [
        f"{symbol} {timeframe} Anchor Trade Entries & Exits",
        "",
        f"Candle range: {_format_time(bars[0].timestamp)} to "
        f"{_format_time(bars[-1].timestamp)}",
        f"Candles: {len(bars)} | Chart pages: {page_count} | "
        f"{candles_per_page} candles ({page_hours:g} hours) per full page",
        f"Trades: {len(trades)} | TP 3%: {outcomes['take_profit']} | "
        f"Locked 1.5%: {outcomes['protected_profit']} | "
        f"SL: {outcomes['stop_loss']} | Unresolved: {outcomes['unresolved']}",
        f"Long: {directions['bullish']} | Short: {directions['bearish']}",
        f"Exit config: SL {stop_loss_ratio:.2%} | Lock {lock_trigger_ratio:.2%} | "
        f"TP {take_profit_ratio:.2%} | "
        f"Gross R:R {take_profit_ratio / stop_loss_ratio:.2f}",
        "",
        "Action convention",
        "  Long:  BUY at entry, SELL at exit",
        "  Short: SELL at entry, BUYBACK at exit",
        "  Green triangle = buy/buyback; red triangle = sell",
        "  Teal dashed line = take profit; orange dashed line = stop loss",
        "  Purple dashed line = 1.5% protected-profit exit",
        "  Gray dotted line = unresolved position",
        "",
        "Continuity",
        "  Chart pages are adjacent and non-overlapping. The candle after the",
        "  final candle on one page is the first candle on the next page.",
        "",
        "Research limitation",
        "  Entries come from post-confirmation structure retest-and-reclaim rules.",
        "  Profit lock activates from the candle after its trigger; OHLC ambiguity",
        "  is resolved conservatively.",
        f"  Costs: entry fee {costs.entry_fee_rate:.2%} | "
        f"exit fee {costs.exit_fee_rate:.2%}",
        f"  Slippage {costs.slippage_rate_per_side:.2%} per side | "
        f"funding {costs.funding_rate:.2%}.",
    ]
    axis.text(
        0.06,
        0.94,
        "\n".join(lines),
        va="top",
        family="monospace",
        fontsize=11,
        linespacing=1.35,
    )
    pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)


def _write_chart_page(
    pdf: PdfPages,
    bars: Sequence[Bar],
    trades: Sequence[AnchorTrade],
    symbol: str,
    timeframe: str,
    page_number: int,
    page_count: int,
) -> None:
    figure = plt.figure(figsize=(16.53, 11.69))
    grid = figure.add_gridspec(2, 1, height_ratios=(4.6, 1.25), hspace=0.18)
    axis = figure.add_subplot(grid[0])
    ledger = figure.add_subplot(grid[1])
    _draw_candles(axis, bars)
    page_trades = draw_page_trades(axis, bars, trades)
    _style_chart(axis, bars, symbol, timeframe, page_number, page_count)
    write_trade_ledger(ledger, page_trades)
    figure.subplots_adjust(left=0.055, right=0.985, top=0.945, bottom=0.055)
    pdf.savefig(figure)
    plt.close(figure)


def _style_chart(
    axis: plt.Axes,
    bars: Sequence[Bar],
    symbol: str,
    timeframe: str,
    page_number: int,
    page_count: int,
) -> None:
    low, high = min(bar.low for bar in bars), max(bar.high for bar in bars)
    padding = max((high - low) * 0.13, high * 0.004)
    axis.set_ylim(low - padding, high + padding)
    axis.set_xlim(-1, len(bars))
    tick_step = max(1, len(bars) // 7)
    ticks = list(range(0, len(bars), tick_step))
    axis.set_xticks(ticks)
    axis.set_xticklabels(
        [
            timestamp_to_utc_plus_8(bars[index].timestamp).strftime("%m-%d\n%H:%M")
            for index in ticks
        ],
        fontsize=7,
    )
    axis.set_ylabel(f"{symbol} price (USDT)")
    axis.set_xlabel("Candle open time (UTC+8)")
    axis.grid(axis="both", alpha=0.18)
    axis.set_title(
        f"{symbol} {timeframe} — {_format_time(bars[0].timestamp)} to "
        f"{_format_time(bars[-1].timestamp)}  |  page {page_number}/{page_count}",
        loc="left",
        fontsize=12,
    )
    axis.legend(
        handles=[
            Line2D([], [], marker="^", color="none", markerfacecolor="#00a651",
                   markeredgecolor="white", markersize=8, label="BUY / BUYBACK"),
            Line2D([], [], marker="v", color="none", markerfacecolor="#d32f2f",
                   markeredgecolor="white", markersize=8, label="SELL"),
            Line2D([], [], color="#00897b", linestyle="--", label="TP trade"),
            Line2D([], [], color="#5e35b1", linestyle="--", label="Locked profit"),
            Line2D([], [], color="#ef6c00", linestyle="--", label="SL trade"),
            Line2D([], [], color="#78909c", linestyle=":", label="Unresolved"),
        ],
        loc="upper left",
        ncol=6,
        fontsize=7,
        framealpha=0.85,
    )


def _validate_continuous_bars(bars: Sequence[Bar]) -> None:
    if not bars:
        raise ValueError("bars must not be empty")
    expected = timedelta(hours=1)
    for previous, current in zip(bars, bars[1:]):
        previous_time = timestamp_to_utc_plus_8(previous.timestamp)
        current_time = timestamp_to_utc_plus_8(current.timestamp)
        if current_time - previous_time != expected:
            raise ValueError(
                f"non-continuous candles: {previous.timestamp} -> {current.timestamp}"
            )


def _format_time(moment: int | str | datetime) -> str:
    return timestamp_to_utc_plus_8(moment).strftime("%Y-%m-%d %H:%M UTC+8")
