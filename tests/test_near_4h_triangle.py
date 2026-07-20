from __future__ import annotations

import json
from pathlib import Path

from core.models import Bar
from indicators.atr import average_true_range
from patterns import PatternDetector, Triangle
from patterns.triangle_contacts import include_closed_shadow_contacts


FIXTURE = Path(__file__).parent / "fixtures" / "near_4h_triangle.json"
LOWER_FIRST = 1_782_864_000_000  # 2026-07-01 08:00 UTC+8
UPPER_FIRST_EARLY = 1_783_080_000_000  # 2026-07-03 20:00 UTC+8
UPPER_FIRST_LATE = 1_783_353_600_000  # 2026-07-07 00:00 UTC+8
LOWER_SECOND = 1_783_915_200_000  # 2026-07-13 12:00 UTC+8
UPPER_SECOND = 1_784_116_800_000  # 2026-07-15 20:00 UTC+8
LOWER_THIRD = 1_784_275_200_000  # 2026-07-17 16:00 UTC+8


def near_bars() -> list[Bar]:
    """Load the closed Binance USD-M NEARUSDT 4h reference interval."""

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Bar(row[0], *row[1:], "4h") for row in rows]


def test_near_triangle_uses_the_supplied_market_leg_anchors() -> None:
    bars = near_bars()
    detector = PatternDetector([Triangle()])
    result = detector.poll_at(bars, "4h", len(bars) - 1)[0].pattern

    assert result.detected is True
    assert result.metadata["triangle_type"] == "ascending_triangle"
    assert result.metadata["structure_span_bars"] == 98
    assert result.metadata["detected_at_index"] == 98
    assert result.metadata["confirmation_grouping"] == (
        "market_leg_with_5_bar_noise_dedup"
    )
    assert result.geometry["upper_timestamps"] == [UPPER_FIRST_EARLY, UPPER_SECOND]
    assert result.geometry["lower_timestamps"] == [
        LOWER_FIRST,
        LOWER_SECOND,
        LOWER_THIRD,
    ]


def test_both_early_upper_wicks_are_valid_first_contact_alternatives() -> None:
    bars = near_bars()
    triangle = Triangle()
    swings = triangle.swing_detector.detect(bars)
    atr = max(average_true_range(bars)[-1], 1e-12)
    highs = include_closed_shadow_contacts(
        bars,
        [point for point in swings if point.kind == "high"],
        upper=True,
        lookback_bars=2,
        shadow_ratio=triangle.min_cluster_shadow_ratio,
    )
    highs = triangle._cluster(bars, highs, atr, upper=True)[
        -triangle.max_swings_per_side :
    ]
    timestamp_sets = {
        tuple(bars[point.index].timestamp for point in points)
        for points, _ in triangle._boundary_candidates(highs, atr, upper=True)
    }

    assert (UPPER_FIRST_EARLY, UPPER_SECOND) in timestamp_sets
    assert (UPPER_FIRST_LATE, UPPER_SECOND) in timestamp_sets
