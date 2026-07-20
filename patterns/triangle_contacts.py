"""Market-leg-aware contact preparation for triangle boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar
from indicators.swing import Pivot


def cluster_boundary_pivots(
    data: Sequence[Bar],
    points: Sequence[Pivot],
    atr: float,
    *,
    upper: bool,
    cluster_bars: int,
    shadow_ratio: float,
    price_tolerance_atr: float,
    opposite_points: Sequence[Pivot] = (),
) -> list[Pivot]:
    """Deduplicate nearby contacts unless an opposite candidate splits the leg."""

    groups = _nearby_groups(points, cluster_bars, opposite_points)
    while True:
        representatives = [
            _representative(
                data,
                group,
                atr,
                upper=upper,
                cluster_bars=cluster_bars,
                shadow_ratio=shadow_ratio,
                price_tolerance_atr=price_tolerance_atr,
                opposite_points=opposite_points,
            )
            for group in groups
        ]
        regrouped = _nearby_groups(representatives, cluster_bars, opposite_points)
        if len(regrouped) == len(representatives):
            return representatives
        groups = regrouped


def include_closed_shadow_contacts(
    data: Sequence[Bar],
    points: Sequence[Pivot],
    *,
    upper: bool,
    lookback_bars: int,
    shadow_ratio: float,
    allowed_indexes: Sequence[int] | None = None,
) -> list[Pivot]:
    """Add recent closed wick contacts without waiting for right-side pivots."""

    existing = {point.index for point in points}
    contacts = list(points)
    start = max(0, len(data) - lookback_bars - 1)
    indexes = range(start, len(data)) if allowed_indexes is None else allowed_indexes
    for index in indexes:
        if index in existing:
            continue
        bar = data[index]
        candle_range = max(bar.high - bar.low, 1e-12)
        body_top = max(bar.open, bar.close)
        body_bottom = min(bar.open, bar.close)
        shadow = bar.high - body_top if upper else body_bottom - bar.low
        if shadow / candle_range < shadow_ratio:
            continue
        price = bar.high if upper else bar.low
        contacts.append(Pivot(index, index, price, "high" if upper else "low"))
    return sorted(contacts, key=lambda point: (point.index, point.confirmed_at))


def _representative(
    data: Sequence[Bar],
    group: Sequence[Pivot],
    atr: float,
    *,
    upper: bool,
    cluster_bars: int,
    shadow_ratio: float,
    price_tolerance_atr: float,
    opposite_points: Sequence[Pivot],
) -> Pivot:
    extreme = (max if upper else min)(group, key=lambda point: point.price)
    confirmed_at = max(point.confirmed_at for point in group)
    tolerance = price_tolerance_atr * atr
    search_start = _search_start(extreme.index, cluster_bars, opposite_points)
    for index in range(search_start, extreme.index + 1):
        bar = data[index]
        candle_range = max(bar.high - bar.low, 1e-12)
        body_top = max(bar.open, bar.close)
        body_bottom = min(bar.open, bar.close)
        shadow = bar.high - body_top if upper else body_bottom - bar.low
        close_to_extreme = (
            bar.high >= extreme.price - tolerance
            if upper
            else bar.low <= extreme.price + tolerance
        )
        if close_to_extreme and shadow / candle_range >= shadow_ratio:
            price = bar.high if upper else bar.low
            return Pivot(index, confirmed_at, price, extreme.kind)
    return Pivot(extreme.index, confirmed_at, extreme.price, extreme.kind)


def _search_start(
    anchor_index: int,
    cluster_bars: int,
    opposite_points: Sequence[Pivot],
) -> int:
    start = max(0, anchor_index - cluster_bars)
    separators = [
        point.index for point in opposite_points if start <= point.index < anchor_index
    ]
    return max(start, max(separators, default=start - 1) + 1)


def _nearby_groups(
    points: Sequence[Pivot],
    cluster_bars: int,
    opposite_points: Sequence[Pivot],
) -> list[list[Pivot]]:
    groups: list[list[Pivot]] = []
    separators = {point.index for point in opposite_points}
    for point in sorted(points, key=lambda item: item.index):
        previous = groups[-1][-1] if groups else None
        separated = previous is not None and any(
            previous.index < index < point.index for index in separators
        )
        nearby = previous is not None and point.index - previous.index <= cluster_bars
        if nearby and not separated:
            groups[-1].append(point)
        else:
            groups.append([point])
    return groups
