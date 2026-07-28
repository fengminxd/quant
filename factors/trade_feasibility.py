"""Post-pattern net reward/risk feasibility scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.base import Factor, Pattern
from core.models import Bar, FactorResult, FeatureResult, PatternResult
from core.pattern_policy import is_trading_pattern_enabled
from features.basic import clamp
from features.trade_feasibility import TransactionCostModel, trade_feasibility_features
from features.trade_plan import PatternTradePlan, PatternTradePlanExtractor
from factors.entry_quality import EntryQualityScore
from indicators.atr import average_true_range


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
    entry_quality: FactorResult | None = None


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
        entry_factor: EntryQualityScore | None = None,
    ) -> None:
        self.extractor = extractor or PatternTradePlanExtractor()
        self.costs = costs or TransactionCostModel()
        self.minimums = dict(DEFAULT_MINIMUM_NET_REWARD_RISK)
        self.minimums.update(minimums or {})
        if any(value <= 0.0 for value in self.minimums.values()):
            raise ValueError("minimum net reward/risk values must be positive")
        self.factor = factor or NetRewardRiskScore()
        self.entry_factor = entry_factor or EntryQualityScore()

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
        window = data[: index + 1]
        entry_assessment = None
        entry_quality = None
        if plan is None and pattern.detected and data[index].timeframe != "1d":
            entry_atr = max(average_true_range(window)[-1], 1e-12)
            entry_assessment = self.extractor.entry_extractor.extract(
                pattern, window, index, entry_atr
            )
            entry_quality = self.entry_factor.calculate(entry_assessment.features)
        extracted, index, atr = self.extractor.extract(
            pattern,
            data,
            as_of_index,
            plan,
            entry_assessment=entry_assessment,
        )
        features = trade_feasibility_features(
            extracted, atr, self.minimums[pattern.pattern_id], self.costs
        )
        raw = self.factor.calculate(features)
        metadata = {
            **raw.metadata,
            "pattern_gate_passed": (
                pattern.detected
                and is_trading_pattern_enabled(pattern.pattern_id)
            ),
            "pattern_enabled": is_trading_pattern_enabled(pattern.pattern_id),
            "pattern_id": pattern.pattern_id,
            "as_of_index": index,
            "entry_fee_rate": self.costs.entry_fee_rate,
            "exit_fee_rate": self.costs.exit_fee_rate,
            "slippage_rate_per_side": self.costs.slippage_rate_per_side,
            "funding_rate": self.costs.funding_rate,
            "stop_buffer_atr": self.extractor.stop_buffer_atr,
            "entry_index": extracted.entry_index if extracted else None,
            "entry_hypothesis": (
                extracted.entry_source if extracted else "waiting_for_structure_retest"
            ),
            "entry_quality_score": entry_quality.score if entry_quality else None,
            "entry_quality_active": (
                entry_quality.metadata.get("active") if entry_quality else None
            ),
            "structure_level": (
                extracted.structure_level if extracted else None
            ),
            "downside_break_required": (
                False if pattern.pattern_id == "PATTERN_002" else None
            ),
            "emits_signal": False,
        }
        result = FactorResult(raw.name, raw.score, raw.features, metadata)
        return PatternTradeFeasibilityEvaluation(
            pattern, extracted, features, result, None, entry_quality
        )

    def score_detected(
        self, patterns: Sequence[PatternResult], data: Sequence[Bar]
    ) -> list[PatternTradeFeasibilityEvaluation]:
        """Score detected patterns with configured reward/risk profiles."""

        return [
            self.score(pattern, data)
            for pattern in patterns
            if (
                pattern.detected
                and is_trading_pattern_enabled(pattern.pattern_id)
                and pattern.pattern_id in self.minimums
            )
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
