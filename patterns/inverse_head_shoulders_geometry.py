"""Geometry gates shared by the inverse-head-and-shoulders detector."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.models import Bar, FeatureResult
from indicators.swing import Pivot


@dataclass(frozen=True)
class InverseHeadShouldersCandidate:
    """Three confirmed swing lows and the two highs forming their neckline."""

    lows: tuple[Pivot, Pivot, Pivot]
    neckline: tuple[Pivot, Pivot]
    atr: float
    breakout_index: int | None
    breakout_distance_atr: float
    breakout_volume_ratio: float


def valid_leg_spans(
    left: Pivot,
    head: Pivot,
    right: Pivot,
    *,
    min_span: int,
    min_leg_span: int,
    min_leg_span_ratio: float | None,
) -> bool:
    """Validate total width, minimum legs, and optional bilateral symmetry."""

    left_leg = head.index - left.index
    right_leg = right.index - head.index
    leg_span_ratio = min(left_leg, right_leg) / max(left_leg, right_leg)
    return (
        right.index - left.index >= min_span
        and left_leg >= min_leg_span
        and right_leg >= min_leg_span
        and (
            min_leg_span_ratio is None
            or leg_span_ratio >= min_leg_span_ratio
        )
    )


def select_neckline(
    highs: Sequence[Pivot],
    left: Pivot,
    head: Pivot,
    right: Pivot,
    *,
    min_leg_span: int,
    atr: float,
    max_price_error_atr: float | None,
) -> tuple[Pivot, Pivot] | None:
    """Select the most horizontal eligible neckline-high pair."""

    left_highs = [
        point
        for point in highs
        if point.index - left.index >= min_leg_span
        and head.index - point.index >= min_leg_span
    ]
    right_highs = [
        point
        for point in highs
        if point.index - head.index >= min_leg_span
        and right.index - point.index >= min_leg_span
    ]
    if not left_highs or not right_highs:
        return None
    if max_price_error_atr is None:
        return max(left_highs, key=lambda point: point.price), max(
            right_highs, key=lambda point: point.price
        )
    eligible = [
        (left_high, right_high)
        for left_high in left_highs
        for right_high in right_highs
        if abs(left_high.price - right_high.price) <= max_price_error_atr * atr
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda pair: (
            abs(pair[0].price - pair[1].price),
            -((pair[0].price + pair[1].price) / 2.0),
            pair[0].index,
            pair[1].index,
        ),
    )


def candidate_features(
    data: Sequence[Bar],
    candidate: InverseHeadShouldersCandidate,
    candidate_count: int,
) -> dict[str, FeatureResult]:
    """Extract explainable geometry, volatility, and confirmation features."""

    left, head, right = candidate.lows
    neck_left, neck_right = candidate.neckline
    left_leg = head.index - left.index
    right_leg = right.index - head.index
    span = right.index - left.index
    prior = data[max(0, left.index - 20) : left.index]
    prior_decline = max((bar.high for bar in prior), default=left.price) - left.price
    return {
        "span": FeatureResult("span", float(span), 1.0),
        "left_leg_span": FeatureResult("left_leg_span", float(left_leg), 1.0),
        "right_leg_span": FeatureResult("right_leg_span", float(right_leg), 1.0),
        "leg_span_difference": FeatureResult(
            "leg_span_difference", float(abs(left_leg - right_leg)), 1.0
        ),
        "leg_span_ratio": FeatureResult(
            "leg_span_ratio", min(left_leg, right_leg) / max(left_leg, right_leg), 1.0
        ),
        "shoulder_price_error_atr": FeatureResult(
            "shoulder_price_error_atr",
            abs(left.price - right.price) / candidate.atr,
            1.0,
        ),
        "head_depth_atr": FeatureResult(
            "head_depth_atr",
            (min(left.price, right.price) - head.price) / candidate.atr,
            1.0,
        ),
        "head_extreme_error_atr": FeatureResult(
            "head_extreme_error_atr",
            (head.price - min(bar.low for bar in data[left.index : right.index + 1]))
            / candidate.atr,
            1.0,
        ),
        "duration_asymmetry": FeatureResult(
            "duration_asymmetry", abs(left_leg - right_leg) / span, 1.0
        ),
        "neckline_slope_atr_per_bar": FeatureResult(
            "neckline_slope_atr_per_bar",
            (neck_right.price - neck_left.price)
            / (neck_right.index - neck_left.index)
            / candidate.atr,
            1.0,
        ),
        "neckline_price_error_atr": FeatureResult(
            "neckline_price_error_atr",
            abs(neck_right.price - neck_left.price) / candidate.atr,
            1.0,
        ),
        "prior_decline_atr": FeatureResult(
            "prior_decline_atr", prior_decline / candidate.atr, 1.0 if prior else 0.0
        ),
        "breakout_confirmed": FeatureResult(
            "breakout_confirmed",
            1.0 if candidate.breakout_index is not None else 0.0,
            1.0,
        ),
        "breakout_distance_atr": FeatureResult(
            "breakout_distance_atr", candidate.breakout_distance_atr, 1.0
        ),
        "breakout_volume_ratio": FeatureResult(
            "breakout_volume_ratio", candidate.breakout_volume_ratio, 1.0
        ),
        "confirmation_lag": FeatureResult(
            "confirmation_lag", float(right.confirmed_at - right.index), 1.0
        ),
        "valid_candidate_count": FeatureResult(
            "valid_candidate_count", float(candidate_count), 1.0
        ),
    }


def candidate_rank(candidate: InverseHeadShouldersCandidate) -> tuple[float, ...]:
    """Rank valid structures by confirmation and price-action quality."""

    left, head, right = candidate.lows
    span = right.index - left.index
    duration_asymmetry = abs(
        (head.index - left.index) - (right.index - head.index)
    ) / span
    return (
        1.0 if candidate.breakout_index is not None else 0.0,
        -abs(candidate.neckline[0].price - candidate.neckline[1].price)
        / candidate.atr,
        -abs(left.price - right.price) / candidate.atr,
        -duration_asymmetry,
        (min(left.price, right.price) - head.price) / candidate.atr,
        float(span),
        float(right.index),
    )
