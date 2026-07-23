"""Reusable traded-price contact rules for horizontal support and resistance."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.models import Bar

PriceZone = tuple[float, float]


@dataclass(frozen=True)
class ContactZoneMatch:
    """A traded-price intersection shared by two explicit anchors."""

    level: float
    gap: float
    overlap_width: float
    left_zone: PriceZone
    right_zone: PriceZone


def upper_resistance_contact_zones(bar: Bar) -> tuple[PriceZone, ...]:
    """Return the source open and upper-shadow traded-price zones."""

    return (
        (bar.open, bar.open),
        (max(bar.open, bar.close), bar.high),
    )


def lower_support_contact_zones(bar: Bar) -> tuple[PriceZone, ...]:
    """Return a support anchor's close and lower-shadow traded-price zones."""

    return (
        (bar.close, bar.close),
        (bar.low, min(bar.open, bar.close)),
    )


def horizontal_resistance_contacts(
    left: Bar,
    right: Bar,
    *,
    price_epsilon: float = 1e-9,
) -> tuple[ContactZoneMatch, ...]:
    """Return every shared open/upper-shadow resistance contact."""

    matches = _contact_zone_matches(
        upper_resistance_contact_zones(left),
        upper_resistance_contact_zones(right),
        price_epsilon=price_epsilon,
        use_overlap_ceiling=True,
    )
    by_level: dict[float, ContactZoneMatch] = {}
    for match in matches:
        previous = by_level.get(match.level)
        if previous is None or match.overlap_width > previous.overlap_width:
            by_level[match.level] = match
    return tuple(
        sorted(by_level.values(), key=lambda match: match.level, reverse=True)
    )


def double_bottom_contact(
    left: Bar,
    right: Bar,
    *,
    price_epsilon: float = 1e-9,
) -> ContactZoneMatch | None:
    """Return the real close/lower-shadow intersection of two low anchors."""

    return _contact_zone_intersection(
        lower_support_contact_zones(left),
        lower_support_contact_zones(right),
        price_epsilon=price_epsilon,
    )


def breakout_retest_contact(
    source: Bar,
    retest: Bar,
    *,
    price_epsilon: float = 1e-9,
) -> ContactZoneMatch | None:
    """Return a real traded-price overlap; never bridge an ATR-sized gap."""

    return _contact_zone_intersection(
        upper_resistance_contact_zones(source),
        lower_support_contact_zones(retest),
        price_epsilon=price_epsilon,
    )


def _contact_zone_intersection(
    left_zones: Sequence[PriceZone],
    right_zones: Sequence[PriceZone],
    *,
    price_epsilon: float,
) -> ContactZoneMatch | None:
    """Select the widest real intersection from two sets of price zones."""

    return max(
        _contact_zone_matches(
            left_zones,
            right_zones,
            price_epsilon=price_epsilon,
            use_overlap_ceiling=False,
        ),
        key=lambda match: (match.overlap_width, -match.gap),
        default=None,
    )


def _contact_zone_matches(
    left_zones: Sequence[PriceZone],
    right_zones: Sequence[PriceZone],
    *,
    price_epsilon: float,
    use_overlap_ceiling: bool,
) -> tuple[ContactZoneMatch, ...]:
    """Return all intersections using midpoint or resistance-ceiling levels."""

    if price_epsilon < 0.0:
        raise ValueError("price_epsilon must be non-negative")
    matches: list[ContactZoneMatch] = []
    for left_zone in left_zones:
        for right_zone in right_zones:
            lower = max(left_zone[0], right_zone[0])
            upper = min(left_zone[1], right_zone[1])
            gap = max(0.0, lower - upper)
            if gap > price_epsilon:
                continue
            overlap = max(0.0, upper - lower)
            level = (
                upper
                if use_overlap_ceiling and gap == 0.0
                else (lower + upper) / 2.0
            )
            matches.append(
                ContactZoneMatch(
                    level,
                    gap,
                    overlap,
                    left_zone,
                    right_zone,
                )
            )
    return tuple(matches)


def body_pierce_count(
    data: Sequence[Bar], left_index: int, right_index: int, level: float
) -> int:
    """Count candle bodies accepting price through a support level."""

    return sum(
        min(bar.open, bar.close) <= level <= max(bar.open, bar.close)
        for bar in data[left_index + 1 : right_index]
    )


def all_closes_above_level(
    data: Sequence[Bar],
    left_index: int,
    right_index: int,
    level: float,
) -> bool:
    """Return whether every intermediate close is strictly above support."""

    return all(
        bar.close > level
        for bar in data[left_index + 1 : right_index]
    )


def first_accepted_breakout(
    data: Sequence[Bar], start_index: int, end_index: int, level: float
) -> int | None:
    """Find the first close accepted above former resistance."""

    return next(
        (
            index
            for index in range(start_index, end_index + 1)
            if data[index].close > level
        ),
        None,
    )


def post_breakout_closes_hold(
    data: Sequence[Bar],
    source_index: int,
    breakout_index: int,
    retest_index: int,
    level: float,
    hold_tolerance: float,
) -> bool:
    """Validate acceptance using a hold tolerance separate from contact."""

    if any(
        bar.close + hold_tolerance < level
        for bar in data[breakout_index : retest_index + 1]
    ):
        return False
    body_pierces = sum(
        min(bar.open, bar.close) <= level <= max(bar.open, bar.close)
        for bar in data[breakout_index + 1 : retest_index]
    )
    if body_pierces > 1:
        return False
    return True
