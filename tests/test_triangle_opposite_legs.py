from __future__ import annotations

from core.models import Bar
from features.basic import fit_regression_line
from indicators.swing import Pivot
from patterns.triangle_contacts import cluster_boundary_pivots
from patterns.triangle_geometry import market_legs_are_complete
from patterns.triangle_validation import opposite_leg_rule_is_valid


def alternating_points() -> list[Pivot]:
    return [
        Pivot(2, 3, 20.0, "high"),
        Pivot(6, 7, 10.0, "low"),
        Pivot(10, 11, 19.0, "high"),
        Pivot(14, 15, 12.0, "low"),
        Pivot(18, 19, 18.0, "high"),
        Pivot(22, 23, 14.0, "low"),
    ]


def base_bars() -> list[Bar]:
    return [Bar(i, 15.0, 15.2, 14.8, 15.0, 1000.0, "4h") for i in range(25)]


def upper_leg_is_valid(bars: list[Bar]) -> bool:
    points = alternating_points()
    upper = tuple(point for point in points if point.kind == "high")
    lower = tuple(point for point in points if point.kind == "low")
    return opposite_leg_rule_is_valid(
        bars,
        same_side=lower,
        selected_opposite=upper,
        opposite_line=fit_regression_line(upper),
        upper=True,
    )


def test_rejects_body_beyond_opposite_projection_after_last_upper_anchor() -> None:
    bars = base_bars()
    bars[20] = Bar(20, 17.6, 18.2, 15.0, 18.0, 1000.0, "4h")

    assert upper_leg_is_valid(bars) is False


def test_allows_shadow_beyond_opposite_projection_after_last_upper_anchor() -> None:
    bars = base_bars()
    bars[20] = Bar(20, 17.4, 18.2, 15.0, 17.5, 1000.0, "4h")

    assert upper_leg_is_valid(bars) is True


def test_allows_another_wick_contact_as_an_anchor_alternative_in_one_leg() -> None:
    bars = [Bar(i, 15.0, 20.2, 14.8, 15.0, 1000.0, "4h") for i in range(41)]
    lower = (Pivot(6, 7, 10.0, "low"), Pivot(20, 21, 12.0, "low"), Pivot(40, 40, 14.0, "low"))
    upper = (Pivot(2, 3, 20.0, "high"), Pivot(12, 13, 19.0, "high"), Pivot(30, 31, 18.0, "high"))
    line = fit_regression_line(upper)

    assert opposite_leg_rule_is_valid(
        bars,
        same_side=lower,
        selected_opposite=upper,
        opposite_line=line,
        upper=True,
    ) is True


def test_opposite_candidate_preserves_nearby_same_side_contacts() -> None:
    bars = base_bars()
    bars[5] = Bar(5, 19.0, 20.0, 18.8, 19.2, 1000.0, "4h")
    bars[9] = Bar(9, 18.8, 19.8, 18.6, 19.0, 1000.0, "4h")
    highs = [Pivot(5, 6, 20.0, "high"), Pivot(9, 10, 19.8, "high")]
    low = Pivot(7, 8, 10.0, "low")

    contacts = cluster_boundary_pivots(
        bars,
        highs,
        2.0,
        upper=True,
        cluster_bars=5,
        shadow_ratio=0.25,
        price_tolerance_atr=0.2,
        opposite_points=[low],
    )

    assert [point.index for point in contacts] == [5, 9]


def test_nearby_contacts_without_opposite_candidate_remain_one_cluster() -> None:
    bars = base_bars()
    bars[5] = Bar(5, 19.0, 20.0, 18.8, 19.2, 1000.0, "4h")
    bars[9] = Bar(9, 18.8, 19.8, 18.6, 19.0, 1000.0, "4h")
    highs = [Pivot(5, 6, 20.0, "high"), Pivot(9, 10, 19.8, "high")]

    contacts = cluster_boundary_pivots(
        bars,
        highs,
        2.0,
        upper=True,
        cluster_bars=5,
        shadow_ratio=0.25,
        price_tolerance_atr=0.2,
    )

    assert [point.index for point in contacts] == [5]


def test_only_selected_opposite_anchor_starts_a_new_market_leg() -> None:
    highs = (Pivot(2, 3, 20.0, "high"), Pivot(22, 23, 19.5, "high"))
    selected_low = (Pivot(12, 13, 10.0, "low"),)
    later_low = (Pivot(32, 33, 11.0, "low"),)

    assert market_legs_are_complete(highs, selected_low) is True
    assert market_legs_are_complete(highs, later_low) is False


def test_market_leg_rejects_nine_bar_adjacent_anchor_span() -> None:
    highs = (Pivot(2, 3, 20.0, "high"), Pivot(22, 23, 19.5, "high"))
    low = (Pivot(11, 12, 10.0, "low"),)

    assert market_legs_are_complete(highs, low) is False
