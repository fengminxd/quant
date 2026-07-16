from __future__ import annotations

from core.models import PatternResult
from factors import SupportLineageScore
from features import support_lineage_features


def pattern_results() -> tuple[PatternResult, PatternResult, PatternResult]:
    inverse = PatternResult(
        "PATTERN_007",
        "Inverse Head and Shoulders",
        True,
        90.8737,
        geometry={"neckline_points": [(280, 429.25), (358, 413.98)]},
    )
    horizontal = PatternResult(
        "PATTERN_004",
        "Horizontal Support",
        True,
        88.1377,
        geometry={"points": [(280, 429.25), (436, 425.08)]},
    )
    trendline = PatternResult(
        "PATTERN_003",
        "Three Point Trendline Support",
        True,
        95.1807,
        geometry={
            "points": [(436, 425.08), (516, 437.44), (532, 443.89)]
        },
    )
    return inverse, horizontal, trendline


def test_zec_neckline_retest_to_trendline_lineage_scores_high() -> None:
    inverse, horizontal, trendline = pattern_results()

    features = support_lineage_features(inverse, horizontal, trendline)
    result = SupportLineageScore().calculate(features)

    assert features["neckline_source_shared"].value == 1.0
    assert features["retest_trendline_anchor_shared"].value == 1.0
    assert features["lineage_span"].value == 252.0
    assert result.metadata["gate_passed"] is True
    assert result.score == 91.7757


def test_lineage_gate_rejects_unrelated_horizontal_source() -> None:
    inverse, horizontal, trendline = pattern_results()
    horizontal = PatternResult(
        horizontal.pattern_id,
        horizontal.name,
        True,
        horizontal.score,
        geometry={"points": [(303, 414.76), (436, 425.08)]},
    )

    result = SupportLineageScore().calculate(
        support_lineage_features(inverse, horizontal, trendline)
    )

    assert result.score == 0.0
    assert result.metadata["gate_passed"] is False
