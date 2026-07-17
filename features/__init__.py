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
from features.ema_rejection import (
    upper_ema_wick_rejection_at_close,
    upper_ema_wick_rejection_indexes,
)
from features.pattern_lineage import support_lineage_features
from features.triangle_context import (
    bearish_triangle_continuation_features,
)
from features.trade_feasibility import TransactionCostModel, trade_feasibility_features
from features.trade_plan import PatternTradePlan, PatternTradePlanExtractor

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
    "PatternTradePlan",
    "PatternTradePlanExtractor",
    "TransactionCostModel",
    "support_lineage_features",
    "bearish_triangle_continuation_features",
    "trade_feasibility_features",
    "upper_ema_wick_rejection_at_close",
    "upper_ema_wick_rejection_indexes",
]
