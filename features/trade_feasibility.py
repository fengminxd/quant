"""Cost-adjusted reward/risk features for an explicit trade plan."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.models import FeatureResult
from features.trade_plan import PatternTradePlan


@dataclass(frozen=True)
class TransactionCostModel:
    """Per-side proportional execution costs plus one holding-cost estimate."""

    fee_rate_per_side: float = 0.0005
    slippage_rate_per_side: float = 0.0002
    funding_rate: float = 0.0

    def __post_init__(self) -> None:
        rates = (self.fee_rate_per_side, self.slippage_rate_per_side, self.funding_rate)
        if any(rate < 0.0 for rate in rates):
            raise ValueError("transaction-cost rates must be non-negative")
        if self.fee_rate_per_side + self.slippage_rate_per_side >= 1.0:
            raise ValueError("per-side execution cost must be less than one")


def trade_feasibility_features(
    plan: PatternTradePlan | None,
    atr: float,
    minimum_net_reward_risk: float,
    costs: TransactionCostModel,
) -> Mapping[str, FeatureResult]:
    """Convert one trade plan into gross and cost-adjusted reward/risk features."""

    if minimum_net_reward_risk <= 0.0:
        raise ValueError("minimum_net_reward_risk must be positive")
    if plan is None:
        return _unavailable_features(minimum_net_reward_risk)
    direction_value = 1.0 if plan.direction == "bullish" else -1.0
    gross_risk = (
        plan.entry_price - plan.stop_price
        if plan.direction == "bullish"
        else plan.stop_price - plan.entry_price
    )
    gross_reward = (
        plan.target_price - plan.entry_price
        if plan.direction == "bullish"
        else plan.entry_price - plan.target_price
    )
    prices = (plan.entry_price, plan.stop_price, plan.target_price)
    valid = gross_risk > 0.0 and gross_reward > 0.0 and all(price > 0.0 for price in prices)
    confidence = float(valid)
    execution_rate = costs.fee_rate_per_side + costs.slippage_rate_per_side
    entry_cost = plan.entry_price * execution_rate
    stop_cost = plan.stop_price * execution_rate
    target_cost = plan.target_price * execution_rate
    funding_cost = plan.entry_price * costs.funding_rate
    net_risk = gross_risk + entry_cost + stop_cost + funding_cost
    net_reward = gross_reward - entry_cost - target_cost - funding_cost
    gross_ratio = gross_reward / gross_risk if valid else 0.0
    net_ratio = net_reward / net_risk if valid and net_risk > 0.0 else 0.0
    cost_r = (entry_cost + target_cost + funding_cost) / gross_risk if valid else 0.0
    values = {
        "plan_available": float(valid),
        "trade_direction": direction_value,
        "entry_index": float(plan.entry_index if plan.entry_index is not None else -1),
        "entry_price": plan.entry_price,
        "stop_price": plan.stop_price,
        "target_price": plan.target_price,
        "gross_risk": gross_risk,
        "gross_reward": gross_reward,
        "net_risk": net_risk,
        "net_reward": net_reward,
        "gross_reward_risk": gross_ratio,
        "net_reward_risk": net_ratio,
        "minimum_net_reward_risk": minimum_net_reward_risk,
        "stop_distance_atr": gross_risk / max(atr, 1e-12),
        "target_distance_atr": gross_reward / max(atr, 1e-12),
        "estimated_cost_r": cost_r,
    }
    return {
        name: FeatureResult(
            name,
            value,
            confidence,
            {"target_source": plan.target_source} if name == "target_price" else {},
        )
        for name, value in values.items()
    }


def _unavailable_features(minimum: float) -> Mapping[str, FeatureResult]:
    names = (
        "plan_available", "trade_direction", "entry_index", "entry_price", "stop_price",
        "target_price", "gross_risk", "gross_reward", "net_risk", "net_reward",
        "gross_reward_risk", "net_reward_risk", "stop_distance_atr",
        "target_distance_atr", "estimated_cost_r",
    )
    features = {name: FeatureResult(name, 0.0, 0.0) for name in names}
    features["minimum_net_reward_risk"] = FeatureResult(
        "minimum_net_reward_risk", minimum, 1.0
    )
    return features
