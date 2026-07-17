from __future__ import annotations

from collections.abc import Sequence

import pytest

from core.models import Bar, PatternResult
from factors.trade_feasibility import NetRewardRiskScore, PatternTradeFeasibilityScorer
from features.trade_feasibility import TransactionCostModel, trade_feasibility_features
from features.trade_plan import PatternTradePlan, PatternTradePlanExtractor
from indicators.swing import Pivot


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


class StaticSwingDetector:
    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        return [Pivot(20, 21, 20.0, "high"), Pivot(30, 31, 10.0, "low")]


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
    costs = TransactionCostModel(0.001, 0.001, 0.001)

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
        plan, 2.0, minimum, TransactionCostModel(0.0, 0.0, 0.0)
    )

    result = NetRewardRiskScore().calculate(features)

    assert result.score == score
    assert result.metadata["feasible"] is feasible
    assert result.metadata["active"] is True


@pytest.mark.parametrize(
    ("pattern_id", "geometry", "direction", "stop_side"),
    [
        ("PATTERN_001", {"points": [(0, 10.0), (40, 11.0)]}, "bullish", "below"),
        ("PATTERN_003", {"line": {"start": (0, 10.0), "end": (40, 11.0)}}, "bullish", "below"),
        ("PATTERN_004", {"level": 11.0}, "bullish", "below"),
        ("PATTERN_005", {"line": {"start": (0, 20.0), "end": (40, 19.0)}}, "bearish", "above"),
        ("PATTERN_006", {"level": 19.0}, "bearish", "above"),
    ],
)
def test_line_and_horizontal_rules_use_structure_stop_and_swing_liquidity(
    pattern_id: str,
    geometry: dict[str, object],
    direction: str,
    stop_side: str,
) -> None:
    pattern = PatternResult(pattern_id, pattern_id, True, 80.0, geometry=geometry)
    extractor = PatternTradePlanExtractor(swing_detector=StaticSwingDetector())

    plan, _, _ = extractor.extract(pattern, bars())

    assert plan is not None
    assert plan.direction == direction
    assert plan.target_source == "confirmed_swing_liquidity"
    assert plan.target_price == (20.0 if direction == "bullish" else 10.0)
    assert (plan.stop_price < plan.entry_price) == (stop_side == "below")


def triangle_pattern(breakout: str | None) -> PatternResult:
    return PatternResult(
        "PATTERN_002",
        "Triangle",
        True,
        70.0,
        geometry={
            "upper_points": [(5, 120.0), (25, 115.0), (45, 110.0)],
            "lower_points": [(10, 80.0), (30, 85.0), (50, 90.0)],
            "upper_line": {"start": (5, 120.0), "end": (45, 110.0)},
            "lower_line": {"start": (10, 80.0), "end": (50, 90.0)},
        },
        metadata={"breakout_direction": breakout, "state": "structure_confirmed"},
    )


def test_triangle_requires_confirmed_breakout_before_feasibility() -> None:
    scorer = PatternTradeFeasibilityScorer(
        costs=TransactionCostModel(0.0, 0.0, 0.0)
    )

    pending = scorer.score(triangle_pattern(None), bars(88.0))
    pending_explicit = scorer.score(
        triangle_pattern(None),
        bars(88.0),
        plan=PatternTradePlan("bearish", 88.0, 92.0, 48.0),
    )
    confirmed = scorer.score(triangle_pattern("downside"), bars(88.0))

    assert pending.plan is None
    assert pending_explicit.plan is None
    assert pending.factor.metadata["state"] == "unavailable"
    assert confirmed.plan is not None
    assert confirmed.plan.direction == "bearish"
    assert confirmed.plan.target_price == pytest.approx(49.25)
    assert confirmed.factor.metadata["target_source"] == "triangle_measured_move"


@pytest.mark.parametrize(
    ("pattern_id", "state", "points", "neckline", "direction", "target"),
    [
        (
            "PATTERN_007", "breakout_confirmed",
            [(5, 10.0), (20, 8.0), (40, 10.0)], [(12, 12.0), (30, 12.0)],
            "bullish", 19.0,
        ),
        (
            "PATTERN_008", "breakdown_confirmed",
            [(5, 20.0), (20, 22.0), (40, 20.0)], [(12, 18.0), (30, 18.0)],
            "bearish", 11.0,
        ),
    ],
)
def test_head_shoulders_rules_use_right_shoulder_stop_and_measured_move(
    pattern_id: str,
    state: str,
    points: list[tuple[int, float]],
    neckline: list[tuple[int, float]],
    direction: str,
    target: float,
) -> None:
    pattern = PatternResult(
        pattern_id,
        pattern_id,
        True,
        80.0,
        geometry={"points": points, "neckline_points": neckline},
        metadata={"state": state},
    )

    plan, _, _ = PatternTradePlanExtractor().extract(pattern, bars())

    assert plan is not None
    assert plan.direction == direction
    assert plan.target_price == pytest.approx(target)
    assert plan.target_source == "head_neckline_measured_move"


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
        costs=TransactionCostModel(0.0, 0.0, 0.0)
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
