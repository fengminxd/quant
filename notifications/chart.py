"""PNG candlestick rendering for Telegram Pattern notifications."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
import os
from pathlib import Path
import tempfile

_matplotlib_cache = Path(tempfile.gettempdir()) / "dp-k-matplotlib"
_matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from core.models import Bar
from notifications.models import NotificationAnchor, NotificationMatch
from research.pattern_lines import pattern_line_groups
from research.pattern_scan import format_utc_plus_8


def render_notification_chart(
    match: NotificationMatch,
    bars: Sequence[Bar],
) -> bytes:
    """Render all 201 candles with Pattern anchors and UTC+8 labels."""

    if len(bars) != 201:
        raise ValueError("notification chart requires exactly 201 bars")
    figure, (price_axis, volume_axis) = plt.subplots(
        2,
        1,
        figsize=(20, 10),
        gridspec_kw={"height_ratios": (4, 1)},
        sharex=True,
    )
    colors = _draw_candles(price_axis, volume_axis, bars)
    _draw_pattern_geometry(price_axis, match)
    _draw_anchors(price_axis, match, bars)
    price_axis.axvline(len(bars) - 1, color="#455a64", linestyle="--", linewidth=0.9)
    price_axis.set_title(
        f"{match.symbol} {match.timeframe} | {match.pattern.pattern_id} "
        f"{match.rule} | score={match.pattern.score:.2f}"
    )
    price_axis.set_ylabel("Price")
    price_axis.grid(axis="y", alpha=0.2)
    volume_axis.bar(range(len(bars)), [bar.volume for bar in bars], color=colors, width=0.65)
    volume_axis.set_ylabel("Volume")
    _set_time_ticks(volume_axis, bars)
    figure.tight_layout()
    output = BytesIO()
    figure.savefig(output, format="png", dpi=140, bbox_inches="tight")
    plt.close(figure)
    return output.getvalue()


def _draw_candles(
    price_axis: plt.Axes,
    volume_axis: plt.Axes,
    bars: Sequence[Bar],
) -> list[str]:
    colors: list[str] = []
    price_range = max(bar.high for bar in bars) - min(bar.low for bar in bars)
    minimum_body = max(price_range * 0.0003, 1e-12)
    for index, bar in enumerate(bars):
        color = "#2e7d32" if bar.close >= bar.open else "#c62828"
        colors.append(color)
        price_axis.vlines(index, bar.low, bar.high, color=color, linewidth=0.65)
        bottom = min(bar.open, bar.close)
        height = max(abs(bar.close - bar.open), minimum_body)
        price_axis.add_patch(
            Rectangle(
                (index - 0.31, bottom),
                0.62,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
            )
        )
    price_axis.set_xlim(-1, len(bars))
    price_axis.autoscale_view()
    volume_axis.set_xlim(-1, len(bars))
    return colors


def _draw_pattern_geometry(axis: plt.Axes, match: NotificationMatch) -> None:
    result = match.pattern
    geometry = result.geometry
    if result.pattern_id in {"PATTERN_004", "PATTERN_005", "PATTERN_006"}:
        for line in pattern_line_groups(result, (), 0):
            _plot_line(axis, line)
        return
    if result.pattern_id in {"PATTERN_007", "PATTERN_008"}:
        points = _numeric_points(geometry.get("points", ()))
        if len(points) >= 2:
            _plot_line(axis, (points[0], points[-1]))
        return
    groups = (
        (geometry.get("upper_points", ()), geometry.get("lower_points", ()))
        if result.pattern_id == "PATTERN_002"
        else (geometry.get("line_contacts", geometry.get("points", ())),)
    )
    for number, raw in enumerate(groups):
        points = _numeric_points(raw)
        if len(points) >= 2:
            _plot_line(
                axis,
                points,
                color=("#1565c0", "#ef6c00", "#6a1b9a")[number % 3],
            )
    neckline = _numeric_points(geometry.get("neckline_points", ()))
    if len(neckline) >= 2:
        axis.plot(
            [point[0] for point in neckline],
            [point[1] for point in neckline],
            color="#ef6c00",
            linestyle="--",
            linewidth=1.15,
            zorder=3,
        )


def _plot_line(
    axis: plt.Axes,
    points: Sequence[tuple[int, float]],
    *,
    color: str = "#1565c0",
) -> None:
    axis.plot(
        [point[0] for point in points],
        [point[1] for point in points],
        color=color,
        linewidth=1.25,
        zorder=3,
    )


def _draw_anchors(
    axis: plt.Axes,
    match: NotificationMatch,
    bars: Sequence[Bar],
) -> None:
    for number, anchor in enumerate(match.anchors):
        color = "#ef6c00" if anchor.label.startswith("N") else "#1565c0"
        price = _chart_anchor_price(match, anchor)
        axis.scatter(anchor.index, price, marker="*", s=90, color=color, zorder=4)
        timestamp = format_utc_plus_8(bars[anchor.index].timestamp).replace(
            ":00 UTC+8", " UTC+8"
        )
        axis.annotate(
            f"{anchor.label}\n{timestamp}",
            (anchor.index, price),
            xytext=(0, 12 if number % 2 == 0 else -28),
            textcoords="offset points",
            ha="center",
            fontsize=6,
            color=color,
        )


def _chart_anchor_price(
    match: NotificationMatch,
    anchor: NotificationAnchor,
) -> float:
    if match.pattern.pattern_id in {"PATTERN_004", "PATTERN_006"}:
        level = match.pattern.geometry.get("level")
        if isinstance(level, (int, float)):
            return float(level)
    return anchor.price


def _numeric_points(raw: object) -> list[tuple[int, float]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [
        (int(point[0]), float(point[1]))
        for point in raw
        if isinstance(point, Sequence)
        and not isinstance(point, (str, bytes))
        and len(point) >= 2
        and isinstance(point[0], (int, float))
        and isinstance(point[1], (int, float))
    ]


def _set_time_ticks(axis: plt.Axes, bars: Sequence[Bar]) -> None:
    indexes = sorted({round(position * 200 / 7) for position in range(8)})
    labels = [
        format_utc_plus_8(bars[index].timestamp).replace(":00 UTC+8", " UTC+8")
        for index in indexes
    ]
    axis.set_xticks(indexes, labels, rotation=25, ha="right", fontsize=8)
