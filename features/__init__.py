"""Reusable feature engineering library."""

from features.basic import (
    atr_compression,
    atr_distance,
    break_count,
    breakout_strength,
    breakout_volume,
    fit_regression_line,
    fit_error,
    higher_low_score,
    line_span,
    resistance_flatness,
    RegressionLine,
    trend_angle,
    trend_strength,
    touch_count,
    volume_contraction,
    volume_ratio,
)
from features.context import ContextFeatureExtractor
from features.pattern_lineage import support_lineage_features

__all__ = [
    "atr_compression",
    "atr_distance",
    "break_count",
    "breakout_strength",
    "breakout_volume",
    "fit_regression_line",
    "fit_error",
    "higher_low_score",
    "line_span",
    "resistance_flatness",
    "RegressionLine",
    "trend_angle",
    "trend_strength",
    "touch_count",
    "volume_contraction",
    "volume_ratio",
    "ContextFeatureExtractor",
    "support_lineage_features",
]
