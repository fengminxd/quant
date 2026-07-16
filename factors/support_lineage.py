"""Score causal support continuation across linked price-action patterns."""

from __future__ import annotations

from collections.abc import Mapping

from core.base import Factor
from core.models import FactorResult, FeatureResult
from features.basic import clamp


class SupportLineageScore(Factor):
    """Score inverse-H&S, neckline retest, and rising-support continuation."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Return zero unless both structural index relationships are exact."""

        complete = _value(features, "support_lineage_complete") >= 1.0
        neckline_shared = _value(features, "neckline_source_shared") >= 1.0
        retest_shared = _value(features, "retest_trendline_anchor_shared") >= 1.0
        if not (complete and neckline_shared and retest_shared):
            return FactorResult(
                "SupportLineageScore",
                0.0,
                _values(features),
                {"active": False, "gate_passed": False},
            )
        inverse = _value(features, "inverse_head_shoulders_quality")
        horizontal = _value(features, "horizontal_retest_quality")
        trendline = _value(features, "trendline_continuation_quality")
        score = clamp(0.30 * inverse + 0.30 * horizontal + 0.40 * trendline)
        return FactorResult(
            "SupportLineageScore",
            round(score, 4),
            _values(features),
            {
                "active": True,
                "gate_passed": True,
                "components": {
                    "inverse_head_shoulders": round(inverse, 4),
                    "horizontal_retest": round(horizontal, 4),
                    "trendline_continuation": round(trendline, 4),
                },
                "weights": {
                    "inverse_head_shoulders": 0.30,
                    "horizontal_retest": 0.30,
                    "trendline_continuation": 0.40,
                },
                "signal_semantics": "score_only",
            },
        )


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].value if name in features else 0.0


def _values(features: Mapping[str, FeatureResult]) -> Mapping[str, float]:
    return {name: result.value for name, result in features.items()}
