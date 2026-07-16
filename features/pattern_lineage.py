"""Features linking a reversal neckline to later support continuation."""

from __future__ import annotations

from collections.abc import Mapping

from core.models import FeatureResult, PatternResult


def support_lineage_features(
    inverse: PatternResult,
    horizontal: PatternResult,
    trendline: PatternResult,
) -> Mapping[str, FeatureResult]:
    """Connect inverse-H&S neckline, horizontal retest, and trendline anchor."""

    detected = inverse.detected and horizontal.detected and trendline.detected
    neckline_indexes = {
        int(point[0]) for point in inverse.geometry.get("neckline_points", ())
    }
    horizontal_points = horizontal.geometry.get("points", ())
    trendline_points = trendline.geometry.get("points", ())
    horizontal_source = _point_index(horizontal_points, 0)
    horizontal_retest = _point_index(horizontal_points, -1)
    trendline_start = _point_index(trendline_points, 0)
    trendline_end = _point_index(trendline_points, -1)
    neckline_shared = detected and horizontal_source in neckline_indexes
    retest_shared = detected and horizontal_retest == trendline_start
    complete = neckline_shared and retest_shared
    confidence = float(detected)
    return {
        "inverse_head_shoulders_quality": FeatureResult(
            "inverse_head_shoulders_quality", inverse.score, float(inverse.detected)
        ),
        "horizontal_retest_quality": FeatureResult(
            "horizontal_retest_quality", horizontal.score, float(horizontal.detected)
        ),
        "trendline_continuation_quality": FeatureResult(
            "trendline_continuation_quality", trendline.score, float(trendline.detected)
        ),
        "neckline_source_shared": FeatureResult(
            "neckline_source_shared", float(neckline_shared), confidence
        ),
        "retest_trendline_anchor_shared": FeatureResult(
            "retest_trendline_anchor_shared", float(retest_shared), confidence
        ),
        "support_lineage_complete": FeatureResult(
            "support_lineage_complete", float(complete), confidence
        ),
        "lineage_span": FeatureResult(
            "lineage_span",
            float(max(0, trendline_end - horizontal_source)) if complete else 0.0,
            confidence,
        ),
    }


def _point_index(points: object, position: int) -> int:
    if not isinstance(points, (list, tuple)) or not points:
        return -1
    point = points[position]
    return int(point[0]) if isinstance(point, (list, tuple)) and point else -1
