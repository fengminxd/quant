from __future__ import annotations

import pytest

from core.models import Bar, PatternResult
from factors.trade_feasibility import NetRewardRiskScore, PatternTradeFeasibilityScorer
from features.trade_feasibility import TransactionCostModel, trade_feasibility_features
from features.trade_plan import PatternTradePlan, PatternTradePlanExtractor


def bars(last_close: float = 15.0) -> list[Bar]:
    result = [Bar(i, 15.0, 15.5, 14.5, 15.0, 1000.0, "4h") for i in range(60)]
    result[-1] = Bar(
        59,
        15.0,
        max(15.5, last_close),
        min(14.5, last_close),
        last_close,
        1000.0,
        "4h",
    )
    return result


def test_transaction_cost_defaults_use_asymmetric_entry_and_exit_fees() -> None:
    costs = TransactionCostModel()

    assert costs.entry_fee_rate == pytest.approx(0.0002)
    assert costs.exit_fee_rate == pytest.approx(0.0005)
    assert costs.slippage_rate_per_side == pytest.approx(0.0002)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_fee_rate": -0.0001},
        {"exit_fee_rate": -0.0001},
        {"entry_fee_rate": 0.9999, "slippage_rate_per_side": 0.0002},
        {"exit_fee_rate": 0.9999, "slippage_rate_per_side": 0.0002},
    ],
)
def test_transaction_cost_model_rejects_invalid_rates(
    kwargs: dict[str, float],
) -> None:
    with pytest.raises(ValueError):
        TransactionCostModel(**kwargs)


@pytest.mark.parametrize(
    ("plan", "expected_net_risk", "expected_net_reward"),
    [
        (PatternTradePlan("bullish", 100.0, 95.0, 110.0), 5.49, 9.48),
        (PatternTradePlan("bearish", 100.0, 105.0, 90.0), 5.51, 9.52),
    ],
)
def test_net_reward_risk_deducts_fee_slippage_and_funding(
    plan: PatternTradePlan,
    expected_net_risk: float,
    expected_net_reward: float,
) -> None:
    costs = TransactionCostModel(
        entry_fee_rate=0.001,
        exit_fee_rate=0.001,
        slippage_rate_per_side=0.001,
        funding_rate=0.001,
    )

    features = trade_feasibility_features(plan, 2.0, 1.5, costs)

    assert features["gross_reward_risk"].value == pytest.approx(2.0)
    assert features["net_risk"].value == pytest.approx(expected_net_risk)
    assert features["net_reward"].value == pytest.approx(expected_net_reward)
    assert features["net_reward_risk"].value < 2.0


@pytest.mark.parametrize(
    ("target", "minimum", "score", "feasible"),
    [(120.0, 2.0, 70.0, True), (115.0, 1.8, 40.0, False), (130.0, 2.0, 100.0, True)],
)
def test_reward_risk_factor_is_continuous_and_has_separate_gate(
    target: float, minimum: float, score: float, feasible: bool
) -> None:
    plan = PatternTradePlan("bullish", 100.0, 90.0, target)
    features = trade_feasibility_features(
        plan,
        2.0,
        minimum,
        TransactionCostModel(
            entry_fee_rate=0.0,
            exit_fee_rate=0.0,
            slippage_rate_per_side=0.0,
        ),
    )

    result = NetRewardRiskScore().calculate(features)

    assert result.score == score
    assert result.metadata["feasible"] is feasible
    assert result.metadata["active"] is True


def test_as_of_scoring_ignores_later_bars_and_rejects_future_confirmation() -> None:
    source = bars()
    pattern = PatternResult(
        "PATTERN_003",
        "Support",
        True,
        80.0,
        geometry={"points": [(0, 10.0), (20, 11.0)]},
        metadata={"detected_at_index": 20},
    )
    plan = PatternTradePlan("bullish", 15.0, 10.0, 25.0)
    scorer = PatternTradeFeasibilityScorer(
        costs=TransactionCostModel(
            entry_fee_rate=0.0,
            exit_fee_rate=0.0,
            slippage_rate_per_side=0.0,
        )
    )

    original = scorer.score(pattern, source, as_of_index=20, plan=plan)
    changed = list(source)
    changed[30:] = [
        Bar(bar.timestamp, 100.0, 110.0, 90.0, 105.0, bar.volume, bar.timeframe)
        for bar in changed[30:]
    ]
    recalculated = scorer.score(pattern, changed, as_of_index=20, plan=plan)

    assert recalculated.factor == original.factor
    with pytest.raises(ValueError, match="precedes pattern confirmation"):
        scorer.score(pattern, source, as_of_index=19, plan=plan)


def test_daily_pattern_cannot_activate_trade_feasibility() -> None:
    source = [
        Bar(i, 15.0, 15.5, 14.5, 15.0, 1000.0, "1d") for i in range(60)
    ]
    pattern = PatternResult(
        "PATTERN_003",
        "Daily Support",
        True,
        80.0,
        geometry={"points": [(0, 10.0), (40, 11.0)]},
    )
    explicit = PatternTradePlan("bullish", 15.0, 10.0, 25.0)

    evaluation = PatternTradeFeasibilityScorer().score(pattern, source, plan=explicit)

    assert evaluation.plan is None
    assert evaluation.factor.metadata["active"] is False
    assert evaluation.factor.metadata["feasible"] is False
