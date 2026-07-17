"""Post-pattern net reward/risk feasibility scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.base import Factor, Pattern
from core.models import Bar, FactorResult, FeatureResult, PatternResult
from features.basic import clamp
from features.trade_feasibility import TransactionCostModel, trade_feasibility_features
from features.trade_plan import (
    PatternTradePlan,
    PatternTradePlanExtractor,
    TradeDirection,
)
from features.triangle_context import bearish_triangle_continuation_features
from factors.triangle_context import TriangleBearishContinuationScore


DEFAULT_MINIMUM_NET_REWARD_RISK: Mapping[str, float] = {
    "PATTERN_001": 1.8,
    "PATTERN_002": 2.0,
    "PATTERN_003": 1.8,
    "PATTERN_004": 2.0,
    "PATTERN_005": 1.8,
    "PATTERN_006": 2.0,
    "PATTERN_007": 2.0,
    "PATTERN_008": 2.0,
}


@dataclass(frozen=True)
class PatternTradeFeasibilityEvaluation:
    """Pattern, derived trade plan, features, and score-only feasibility result."""

    pattern: PatternResult
    plan: PatternTradePlan | None
    features: Mapping[str, FeatureResult]
    factor: FactorResult
    directional_context: FactorResult | None = None


class NetRewardRiskScore(Factor):
    """Score net reward/risk continuously without emitting a trade signal."""

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Map net R to 0-100 and expose a separate minimum-R feasibility gate."""

        available = _value(features, "plan_available") > 0.0
        net_reward = _value(features, "net_reward")
        ratio = _value(features, "net_reward_risk")
        minimum = _value(features, "minimum_net_reward_risk")
        active = available
        feasible = active and net_reward > 0.0 and ratio >= minimum
        score = _ratio_score(ratio) if active and net_reward > 0.0 else 0.0
        state = "feasible" if feasible else "insufficient_net_r"
        if not active:
            state = "unavailable"
        elif net_reward <= 0.0:
            state = "non_positive_net_reward"
        target = features.get("target_price")
        target_source = target.metadata.get("target_source") if target else None
        return FactorResult(
            "NetRewardRiskScore",
            round(clamp(score), 4),
            {name: feature.value for name, feature in features.items()},
            {
                "active": active,
                "feasible": feasible,
                "state": state,
                "net_reward_risk": round(ratio, 6),
                "minimum_net_reward_risk": minimum,
                "target_source": target_source,
                "confidence": features.get(
                    "plan_available", FeatureResult("plan_available", 0.0, 0.0)
                ).confidence,
            },
        )


class PatternTradeFeasibilityScorer:
    """Run only after Pattern detection and keep feasibility independent."""

    def __init__(
        self,
        extractor: PatternTradePlanExtractor | None = None,
        costs: TransactionCostModel | None = None,
        minimums: Mapping[str, float] | None = None,
        factor: NetRewardRiskScore | None = None,
    ) -> None:
        self.extractor = extractor or PatternTradePlanExtractor()
        self.costs = costs or TransactionCostModel()
        self.minimums = dict(DEFAULT_MINIMUM_NET_REWARD_RISK)
        self.minimums.update(minimums or {})
        if any(value <= 0.0 for value in self.minimums.values()):
            raise ValueError("minimum net reward/risk values must be positive")
        self.factor = factor or NetRewardRiskScore()

    def evaluate(
        self,
        pattern: Pattern,
        data: Sequence[Bar],
        as_of_index: int | None = None,
    ) -> PatternTradeFeasibilityEvaluation:
        """Detect and score on a historical window without exposing future bars."""

        if not data:
            raise ValueError("at least one bar is required")
        index = len(data) - 1 if as_of_index is None else as_of_index
        if index < 0 or index >= len(data):
            raise ValueError("as_of_index is outside supplied data")
        window = data[: index + 1]
        return self.score(pattern.detect(window), window)

    def score(
        self,
        pattern: PatternResult,
        data: Sequence[Bar],
        as_of_index: int | None = None,
        plan: PatternTradePlan | None = None,
    ) -> PatternTradeFeasibilityEvaluation:
        """Score one detected PatternResult using a derived or explicit plan."""

        if pattern.pattern_id not in self.minimums:
            raise ValueError(f"no reward/risk profile for {pattern.pattern_id}")
        index = len(data) - 1 if as_of_index is None else as_of_index
        if index < 0 or index >= len(data):
            raise ValueError("as_of_index is outside supplied data")
        direction, entry_index, directional_context = _triangle_continuation_entry(
            pattern, data[: index + 1]
        )
        extracted, index, atr = self.extractor.extract(
            pattern,
            data,
            as_of_index,
            plan,
            direction_override=direction,
            entry_index=entry_index,
            triangle_entry_mode=(
                "upper_boundary_ema_rejection" if direction else None
            ),
        )
        features = trade_feasibility_features(
            extracted, atr, self.minimums[pattern.pattern_id], self.costs
        )
        raw = self.factor.calculate(features)
        metadata = {
            **raw.metadata,
            "pattern_gate_passed": pattern.detected,
            "pattern_id": pattern.pattern_id,
            "as_of_index": index,
            "fee_rate_per_side": self.costs.fee_rate_per_side,
            "slippage_rate_per_side": self.costs.slippage_rate_per_side,
            "funding_rate": self.costs.funding_rate,
            "stop_buffer_atr": self.extractor.stop_buffer_atr,
            "entry_index": extracted.entry_index if extracted else None,
            "entry_hypothesis": (
                "third_upper_ema_rejection" if direction else "pattern_default"
            ),
            "directional_context_score": (
                directional_context.score if directional_context else None
            ),
            "downside_break_required": False if direction else None,
            "emits_signal": False,
        }
        result = FactorResult(raw.name, raw.score, raw.features, metadata)
        return PatternTradeFeasibilityEvaluation(
            pattern, extracted, features, result, directional_context
        )

    def score_detected(
        self, patterns: Sequence[PatternResult], data: Sequence[Bar]
    ) -> list[PatternTradeFeasibilityEvaluation]:
        """Score detected patterns with configured reward/risk profiles."""

        return [
            self.score(pattern, data)
            for pattern in patterns
            if pattern.detected and pattern.pattern_id in self.minimums
        ]


def _ratio_score(ratio: float) -> float:
    if ratio <= 1.0:
        return 0.0
    if ratio <= 1.5:
        return (ratio - 1.0) / 0.5 * 40.0
    if ratio <= 2.0:
        return 40.0 + (ratio - 1.5) / 0.5 * 30.0
    if ratio <= 3.0:
        return 70.0 + (ratio - 2.0) * 30.0
    return 100.0


def _value(features: Mapping[str, FeatureResult], name: str) -> float:
    return features[name].value if name in features else 0.0


def _triangle_continuation_entry(
    pattern: PatternResult,
    data: Sequence[Bar],
) -> tuple[TradeDirection | None, int | None, FactorResult | None]:
    if (
        not pattern.detected
        or pattern.pattern_id != "PATTERN_002"
        or pattern.metadata.get("breakout_direction") is not None
    ):
        return None, None, None
    try:
        features = bearish_triangle_continuation_features(data, pattern)
    except (KeyError, ValueError):
        return None, None, None
    context = TriangleBearishContinuationScore().calculate(features)
    if not bool(context.metadata.get("active", False)):
        return None, None, context
    points = pattern.geometry.get("upper_points", ())
    if not isinstance(points, Sequence) or len(points) != 3:
        return None, None, context
    offset = pattern.metadata.get("window_start_index", 0)
    global_offset = int(offset) if isinstance(offset, (int, float)) else 0
    entry_index = int(points[-1][0]) + global_offset
    return "bearish", entry_index, context
