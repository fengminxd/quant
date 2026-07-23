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
from indicators.ema import exponential_moving_average
from research.pattern_scan import PatternScanEvent, format_utc_plus_8
from visualization.pattern_text import event_title, level_relation_kind


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
    priority_count = sum(event.priority_fixed_combination for event in events)
    lines.extend(("", f"Priority fixed combinations: {priority_count}"))
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
    figure.tight_layout(pad=2.0)
    pdf.savefig(figure)
    plt.close(figure)


def _draw_event(
    axis: plt.Axes,
    bars: Sequence[Bar],
    event: PatternScanEvent,
) -> None:
    sources = event.displayed_level_sources
    start = min((event.first_anchor_index, *(anchor.index for anchor in sources)))
    relation_targets = tuple(
        relation.target.index for relation in event.priority_level_relations
    )
    end = max((event.last_anchor_index, *relation_targets))
    span = bars[start : end + 1]
    _draw_candles(axis, span)
    _draw_ema99(axis, bars, start, end)
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
    _draw_level_relations(axis, event, start)
    related_keys = {
        (relation.source.index, relation.source.price)
        for relation in event.priority_level_relations
    }
    legacy_sources = tuple(
        anchor
        for anchor in sources
        if (anchor.index, anchor.price) not in related_keys
    )
    for number, anchor in enumerate(legacy_sources, start=1):
        x_value = anchor.index - start
        axis.scatter(
            x_value,
            anchor.price,
            marker="D",
            s=45,
            color="#ef6c00",
            zorder=4,
        )
        axis.annotate(
            f"L{number}\n{format_utc_plus_8(anchor.timestamp)}",
            (x_value, anchor.price),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=5.5,
            color="#e65100",
        )
    axis.set_title(event_title(event), fontsize=8, loc="left")
    axis.set_ylabel("Price", fontsize=8)
    axis.grid(axis="y", alpha=0.2)
    axis.legend(loc="upper left", fontsize=6, framealpha=0.75)
    _set_time_ticks(axis, span)


def _draw_ema99(
    axis: plt.Axes,
    bars: Sequence[Bar],
    start: int,
    end: int,
) -> None:
    """Draw same-timeframe EMA99 calculated from all preceding visible history."""

    if not bars or start > end:
        return
    values = exponential_moving_average(bars, period=99)
    axis.plot(
        range(end - start + 1),
        values[start : end + 1],
        color="#8e24aa",
        linewidth=1.1,
        label="EMA99",
        zorder=2,
    )


def _draw_level_relations(
    axis: plt.Axes,
    event: PatternScanEvent,
    start: int,
) -> None:
    """Mark and connect every historical support/resistance evidence anchor."""

    for number, relation in enumerate(event.priority_level_relations, start=1):
        prefix, label, color = level_relation_kind(relation.rule_type)
        source_x = relation.source.index - start
        target_x = relation.target.index - start
        axis.plot(
            (source_x, target_x),
            (relation.level, relation.level),
            color=color,
            linestyle=":",
            linewidth=1.0,
            label=f"Combo {label}" if number == 1 else "_nolegend_",
            zorder=2,
        )
        axis.scatter(
            source_x,
            relation.level,
            marker="D",
            s=48,
            color=color,
            zorder=4,
        )
        axis.annotate(
            f"{prefix}{number}: {label}\n"
            f"{format_utc_plus_8(relation.source.timestamp)}",
            (source_x, relation.level),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=5.5,
            color=color,
        )


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
