"""Per-symbol PDF reports for historical Pattern scan events."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.collections import LineCollection, PolyCollection

from core.models import Bar
from research.pattern_scan import PatternScanEvent, format_utc_plus_8


def write_symbol_pdf(
    symbol: str,
    bars_by_timeframe: Mapping[str, Sequence[Bar]],
    events: Sequence[PatternScanEvent],
    output_path: str | Path,
) -> Path:
    """Write one summary page and one candlestick page per detected structure."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered_events = sorted(
        events,
        key=lambda event: (event.timeframe, event.first_anchor_index, event.pattern_id),
    )
    with PdfPages(target) as pdf:
        _write_summary_page(pdf, symbol, bars_by_timeframe, ordered_events)
        for start in range(0, len(ordered_events), 4):
            _write_event_grid(
                pdf,
                bars_by_timeframe,
                ordered_events[start : start + 4],
            )
    return target


def _write_summary_page(
    pdf: PdfPages,
    symbol: str,
    bars_by_timeframe: Mapping[str, Sequence[Bar]],
    events: Sequence[PatternScanEvent],
) -> None:
    figure, axis = plt.subplots(figsize=(11.69, 8.27))
    axis.axis("off")
    counts = Counter((event.timeframe, event.pattern_id) for event in events)
    lines = [
        f"Historical Pattern Scan: {symbol}",
        "Patterns: PATTERN_002 through PATTERN_008 (PATTERN_001 excluded)",
        f"Detected structures: {len(events)}",
        "",
    ]
    for timeframe in sorted(bars_by_timeframe, key=lambda value: (value != "1h", value)):
        bars = bars_by_timeframe.get(timeframe, ())
        period = "no data"
        if bars:
            period = (
                f"{format_utc_plus_8(bars[0].timestamp)} to "
                f"{format_utc_plus_8(bars[-1].timestamp)}"
            )
        lines.append(f"{timeframe}: {len(bars)} candles, {period}")
        pattern_counts = [
            f"{pattern_id}={counts[(timeframe, pattern_id)]}"
            for pattern_id in (f"PATTERN_{number:03d}" for number in range(2, 9))
        ]
        lines.append("    " + ", ".join(pattern_counts))
    axis.text(0.05, 0.95, "\n".join(lines), va="top", family="monospace", fontsize=11)
    pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)


def _write_event_grid(
    pdf: PdfPages,
    bars_by_timeframe: Mapping[str, Sequence[Bar]],
    events: Sequence[PatternScanEvent],
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(16.53, 11.69))
    flat_axes = list(axes.flat)
    for axis, event in zip(flat_axes, events):
        _draw_event(axis, bars_by_timeframe[event.timeframe], event)
    for axis in flat_axes[len(events) :]:
        axis.axis("off")
    figure.tight_layout()
    pdf.savefig(figure)
    plt.close(figure)


def _draw_event(
    axis: plt.Axes,
    bars: Sequence[Bar],
    event: PatternScanEvent,
) -> None:
    span = bars[event.first_anchor_index : event.last_anchor_index + 1]
    _draw_candles(axis, span)
    start = event.first_anchor_index
    line_groups = event.line_groups or event.anchor_groups or (event.anchors,)
    colors = ("#1565c0", "#ef6c00", "#6a1b9a")
    for group_number, group in enumerate(line_groups):
        ordered = sorted(group, key=lambda anchor: anchor.index)
        axis.plot(
            [anchor.index - start for anchor in ordered],
            [anchor.price for anchor in ordered],
            color=colors[group_number % len(colors)],
            linewidth=1.25,
            zorder=3,
        )
    for number, anchor in enumerate(event.anchors, start=1):
        x_value = anchor.index - start
        axis.scatter(x_value, anchor.price, marker="*", s=110, color="#1565c0", zorder=4)
        axis.annotate(
            f"A{number}\n{format_utc_plus_8(anchor.timestamp)}",
            (x_value, anchor.price),
            xytext=(0, 9 if number % 2 else -22),
            textcoords="offset points",
            ha="center",
            fontsize=5.5,
            color="#0d47a1",
        )
    axis.set_title(
        f"{event.symbol} {event.timeframe} | {event.pattern_id} {event.pattern_name}\n"
        f"rule={event.rule} | score={event.score:.2f}",
        fontsize=9,
    )
    axis.set_ylabel("Price", fontsize=8)
    axis.grid(axis="y", alpha=0.2)
    _set_time_ticks(axis, span)


def _draw_candles(axis: plt.Axes, bars: Sequence[Bar]) -> None:
    if not bars:
        return
    price_range = max(bar.high for bar in bars) - min(bar.low for bar in bars)
    minimum_body = max(price_range * 0.0005, 1e-12)
    wick_segments = []
    body_polygons = []
    colors = []
    for index, bar in enumerate(bars):
        rising = bar.close >= bar.open
        color = "#2e7d32" if rising else "#c62828"
        body_bottom = min(bar.open, bar.close)
        body_height = max(abs(bar.close - bar.open), minimum_body)
        wick_segments.append(((index, bar.low), (index, bar.high)))
        body_polygons.append(
            (
                (index - 0.32, body_bottom),
                (index + 0.32, body_bottom),
                (index + 0.32, body_bottom + body_height),
                (index - 0.32, body_bottom + body_height),
            )
        )
        colors.append(color)
    axis.add_collection(LineCollection(wick_segments, colors=colors, linewidths=0.8))
    axis.add_collection(
        PolyCollection(body_polygons, facecolors=colors, edgecolors=colors, linewidths=0.5)
    )
    axis.autoscale_view()
    axis.set_xlim(-1, len(bars))


def _set_time_ticks(axis: plt.Axes, bars: Sequence[Bar]) -> None:
    if not bars:
        return
    tick_count = min(6, len(bars))
    if tick_count == 1:
        indexes = [0]
    else:
        indexes = sorted(
            {round(position * (len(bars) - 1) / (tick_count - 1)) for position in range(tick_count)}
        )
    labels = [format_utc_plus_8(bars[index].timestamp).replace(":00 UTC+8", " UTC+8") for index in indexes]
    axis.set_xticks(indexes, labels, rotation=25, ha="right", fontsize=8)
