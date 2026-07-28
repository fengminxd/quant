"""Trade paths, action markers, and page ledger for candlestick reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Sequence

import matplotlib.pyplot as plt

from backtest.trade_outcome_labels import AnchorTrade, timestamp_to_utc_plus_8
from core.models import Bar


def draw_page_trades(
    axis: plt.Axes,
    bars: Sequence[Bar],
    trades: Sequence[AnchorTrade],
) -> list[AnchorTrade]:
    """Draw paths and actions that intersect the current candle page."""

    first_time = timestamp_to_utc_plus_8(bars[0].timestamp)
    last_time = timestamp_to_utc_plus_8(bars[-1].timestamp)
    page_trades = [
        trade
        for trade in trades
        if first_time <= trade.entry_time <= last_time
        or trade.exit_time is not None
        and first_time <= trade.exit_time <= last_time
    ]
    offsets: defaultdict[tuple[datetime, str], int] = defaultdict(int)
    for trade in trades:
        _draw_trade_path(axis, trade, first_time, last_time)
        if first_time <= trade.entry_time <= last_time:
            action = "BUY" if trade.direction == "bullish" else "SELL"
            _draw_action(axis, bars, trade, trade.entry_time, trade.entry, action, offsets)
        if trade.exit_time is not None and first_time <= trade.exit_time <= last_time:
            action = "SELL" if trade.direction == "bullish" else "BUYBACK"
            exit_price = trade.exit_price or _fallback_exit_price(trade)
            _draw_action(
                axis,
                bars,
                trade,
                trade.exit_time,
                exit_price,
                action,
                offsets,
                trade.outcome,
            )
    return page_trades


def write_trade_ledger(axis: plt.Axes, trades: Sequence[AnchorTrade]) -> None:
    """Write the per-page trade index below its chart."""

    axis.axis("off")
    if not trades:
        axis.text(0.01, 0.9, "No entries or exits on this page.", va="top", fontsize=8)
        return
    lines = []
    for trade in sorted(trades, key=lambda item: (item.entry_time, item.trade_id)):
        side = "LONG" if trade.direction == "bullish" else "SHORT"
        exit_text = _format_short_time(trade.exit_time) if trade.exit_time else "OPEN"
        lines.append(
            f"T{trade.trade_id:02d} {side:<5} {trade.pattern[-3:]} "
            f"{trade.outcome.upper():<11} "
            f"IN {_format_short_time(trade.entry_time)} @{trade.entry:,.1f}  "
            f"OUT {exit_text}"
        )
    midpoint = (len(lines) + 1) // 2
    axis.text(
        0.01,
        0.98,
        "\n".join(lines[:midpoint]),
        va="top",
        family="monospace",
        fontsize=6.1,
        linespacing=1.2,
    )
    axis.text(
        0.51,
        0.98,
        "\n".join(lines[midpoint:]),
        va="top",
        family="monospace",
        fontsize=6.1,
        linespacing=1.2,
    )


def _draw_trade_path(
    axis: plt.Axes,
    trade: AnchorTrade,
    first_time: datetime,
    last_time: datetime,
) -> None:
    path_end = trade.exit_time or last_time
    if path_end < first_time or trade.entry_time > last_time:
        return
    clipped_start = max(trade.entry_time, first_time)
    clipped_end = min(path_end, last_time)
    end_price = trade.exit_price or _fallback_exit_price(trade)
    duration = max((path_end - trade.entry_time).total_seconds(), 1.0)

    def interpolated(moment: datetime) -> float:
        ratio = (moment - trade.entry_time).total_seconds() / duration
        return trade.entry + ratio * (end_price - trade.entry)

    color = {
        "take_profit": "#00897b",
        "protected_profit": "#5e35b1",
        "stop_loss": "#ef6c00",
        "unresolved": "#78909c",
    }.get(trade.outcome, "#78909c")
    axis.plot(
        [_hour_index(clipped_start, first_time), _hour_index(clipped_end, first_time)],
        [interpolated(clipped_start), interpolated(clipped_end)],
        color=color,
        linestyle="--" if trade.outcome != "unresolved" else ":",
        linewidth=0.75,
        alpha=0.55,
        zorder=2,
    )


def _draw_action(
    axis: plt.Axes,
    bars: Sequence[Bar],
    trade: AnchorTrade,
    moment: datetime,
    price: float,
    action: str,
    offsets: defaultdict[tuple[datetime, str], int],
    outcome: str | None = None,
) -> None:
    is_buy = action in {"BUY", "BUYBACK"}
    color, marker = ("#00a651", "^") if is_buy else ("#d32f2f", "v")
    x_value = _hour_index(moment, timestamp_to_utc_plus_8(bars[0].timestamp))
    axis.scatter(
        x_value,
        price,
        marker=marker,
        s=62,
        facecolor=color,
        edgecolor="white",
        linewidth=0.6,
        zorder=5,
    )
    key = (moment, action)
    collision = offsets[key]
    offsets[key] += 1
    base = 13 if is_buy else -29
    vertical = base + (collision * 16 if is_buy else collision * -16)
    suffix = f" {outcome.replace('_', ' ').upper()}" if outcome else ""
    axis.annotate(
        f"T{trade.trade_id:02d} {action}{suffix}\n{_format_short_time(moment)}",
        (x_value, price),
        xytext=(0, vertical),
        textcoords="offset points",
        ha="center",
        va="bottom" if is_buy else "top",
        fontsize=5.2,
        color=color,
        bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": color, "alpha": 0.8},
        arrowprops={"arrowstyle": "-", "color": color, "lw": 0.45},
        annotation_clip=True,
        zorder=6,
    )


def _hour_index(moment: datetime, first_time: datetime) -> float:
    return (moment - first_time).total_seconds() / 3600.0


def _format_short_time(moment: datetime) -> str:
    return moment.strftime("%m-%d %H:%M UTC+8")


def _fallback_exit_price(trade: AnchorTrade) -> float:
    if trade.outcome == "take_profit":
        return trade.target
    if trade.outcome == "protected_profit":
        return trade.locked_stop or trade.entry
    if trade.outcome == "stop_loss":
        return trade.stop
    return trade.entry
