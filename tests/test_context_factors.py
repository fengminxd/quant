from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from core.base import Factor, Pattern
from core.models import Bar, FactorResult, FeatureResult, PatternResult
from factors.context_factors import (
    DowntrendStructureScore,
    EMA99ContextScore,
    HammerScore,
    InvertedHammerScore,
    PriorHighBreakoutScore,
    PriorLowBreakdownScore,
    UptrendStructureScore,
)
from factors.pattern_context import (
    FactorSpec,
    PatternContextScorer,
    PatternFactorProfile,
)
from features.context import ContextFeatureExtractor
from indicators.ema import exponential_moving_average
from indicators.swing import PivotDetector, SwingDetector


def bars_from_centers(centers: Sequence[float]) -> list[Bar]:
    return [
        Bar(index, center, center + 0.2, center - 0.2, center + 0.05, 1000.0)
        for index, center in enumerate(centers)
    ]


def context_extractor() -> ContextFeatureExtractor:
    swing = SwingDetector(PivotDetector(left=1, right=1), min_bars=1)
    return ContextFeatureExtractor(swing_detector=swing)


def pattern_result(pattern_id: str, detected: bool = True) -> PatternResult:
    return PatternResult(
        pattern_id,
        f"Pattern {pattern_id}",
        detected,
        80.0 if detected else 0.0,
        geometry={"points": [(1, 10.0)]} if detected else {},
        metadata={"detected_at_index": 1} if detected else {},
    )


def test_ema_is_causal_and_uses_the_requested_period() -> None:
    bars = bars_from_centers([1.0, 2.0, 3.0])
    changed_future = bars_from_centers([1.0, 2.0, 30.0])

    values = exponential_moving_average(bars, period=3)
    changed = exponential_moving_average(changed_future, period=3)

    assert values == pytest.approx([1.05, 1.55, 2.3])
    assert changed[:2] == pytest.approx(values[:2])


def test_ema_can_continue_a_prior_causal_state() -> None:
    bars = bars_from_centers([2.0, 3.0])

    values = exponential_moving_average(bars, period=3, initial_value=1.0)

    assert values == pytest.approx([1.525, 2.2875])


def test_uptrend_and_breakout_factors_use_confirmed_swings() -> None:
    bars = bars_from_centers([10, 12, 11, 14, 12, 16, 13, 18, 14, 19])
    features = context_extractor().extract(bars)

    uptrend = UptrendStructureScore().calculate(features)
    downtrend = DowntrendStructureScore().calculate(features)
    breakout = PriorHighBreakoutScore().calculate(features)

    assert uptrend.metadata["active"] is True
    assert uptrend.score > downtrend.score
    assert breakout.metadata["state"] == "breakout"
    assert breakout.score > 50.0
    assert features["prior_swing_high"].value == pytest.approx(18.2)


def test_downtrend_and_breakdown_factors_use_confirmed_swings() -> None:
    bars = bars_from_centers([20, 18, 19, 16, 18, 14, 17, 12, 16, 11])
    features = context_extractor().extract(bars)

    uptrend = UptrendStructureScore().calculate(features)
    downtrend = DowntrendStructureScore().calculate(features)
    breakdown = PriorLowBreakdownScore().calculate(features)

    assert downtrend.metadata["active"] is True
    assert downtrend.score > uptrend.score
    assert breakdown.metadata["state"] == "breakdown"
    assert breakdown.score > 50.0
    assert features["prior_swing_low"].value == pytest.approx(11.8)


def test_ema99_requires_full_warmup_before_becoming_active() -> None:
    short = context_extractor().extract(bars_from_centers(range(50)))
    long = context_extractor().extract(bars_from_centers(range(120)))

    short_result = EMA99ContextScore().calculate(short)
    long_result = EMA99ContextScore().calculate(long)

    assert short_result.metadata["active"] is False
    assert long_result.metadata["active"] is True
    assert long_result.score > 50.0


def test_hammer_and_inverted_hammer_are_continuous_geometry_factors() -> None:
    hammer_bar = Bar(0, 10.0, 10.1, 8.0, 9.9, 1000.0)
    inverted_bar = Bar(0, 9.0, 11.0, 8.9, 9.1, 1000.0)

    hammer_features = context_extractor().extract([hammer_bar])
    inverted_features = context_extractor().extract([inverted_bar])
    hammer = HammerScore().calculate(hammer_features)
    inverted = InvertedHammerScore().calculate(inverted_features)

    assert hammer.metadata["active"] is True
    assert hammer.score > 70.0
    assert inverted.metadata["active"] is True
    assert inverted.score > 70.0


@pytest.mark.parametrize(
    ("pattern_id", "included", "excluded"),
    [
        ("PATTERN_003", "HammerScore", "InvertedHammerScore"),
        ("PATTERN_004", "HammerScore", "InvertedHammerScore"),
        ("PATTERN_005", "InvertedHammerScore", "HammerScore"),
        ("PATTERN_006", "InvertedHammerScore", "HammerScore"),
        ("PATTERN_007", "HammerScore", None),
        ("PATTERN_008", "InvertedHammerScore", None),
    ],
)
def test_six_patterns_select_configured_context_factors(
    pattern_id: str, included: str, excluded: str | None
) -> None:
    bars = bars_from_centers([10, 12, 11, 14, 12, 16, 13, 18, 14, 19])
    scorer = PatternContextScorer(extractor=context_extractor())

    evaluation = scorer.score(pattern_result(pattern_id), bars)
    selected = evaluation.composite.metadata["selected_factors"]

    assert evaluation.composite.metadata["gate_passed"] is True
    assert included in selected
    if excluded is not None:
        assert excluded not in selected
    if pattern_id in {"PATTERN_007", "PATTERN_008"}:
        assert {"HammerScore", "InvertedHammerScore"} <= set(selected)
    assert 0.0 <= evaluation.composite.score <= 100.0


def test_undetected_pattern_does_not_run_context_factors() -> None:
    bars = bars_from_centers([10, 11, 12, 13, 14])

    evaluation = PatternContextScorer().score(pattern_result("PATTERN_003", False), bars)

    assert evaluation.factors == {}
    assert evaluation.composite.score == 0.0
    assert evaluation.composite.metadata["gate_passed"] is False


class LengthGatedPattern(Pattern):
    pattern_id = "PATTERN_003"
    name = "Length Gated Support"

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        detected = len(data) >= 10
        return PatternResult(
            self.pattern_id,
            self.name,
            detected,
            80.0 if detected else 0.0,
            geometry={"points": [(9, data[9].low)]} if detected else {},
            metadata={"detected_at_index": 9} if detected else {},
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        return {}

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        return 80.0

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        return result.geometry


def test_evaluate_truncates_before_pattern_detection() -> None:
    bars = bars_from_centers(range(12))
    scorer = PatternContextScorer(extractor=context_extractor())

    before = scorer.evaluate(LengthGatedPattern(), bars, as_of_index=8)
    after = scorer.evaluate(LengthGatedPattern(), bars, as_of_index=9)

    assert before.composite.metadata["gate_passed"] is False
    assert after.composite.metadata["gate_passed"] is True


class FixedFactor(Factor):
    def __init__(self, name: str, score: float, active: bool) -> None:
        self.name = name
        self.score = score
        self.active = active

    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        return FactorResult(
            self.name,
            self.score,
            metadata={"active": self.active, "confidence": 1.0},
        )


def test_composite_uses_fixed_weights_polarity_and_neutral_inactive_score() -> None:
    profile = PatternFactorProfile(
        "PATTERN_003",
        "bullish",
        0.50,
        (FactorSpec("Positive", 0.25), FactorSpec("Negative", 0.25, -1)),
    )
    factors: Mapping[str, Factor] = {
        "Positive": FixedFactor("Positive", 90.0, False),
        "Negative": FixedFactor("Negative", 80.0, True),
    }
    scorer = PatternContextScorer(
        extractor=context_extractor(),
        profiles={"PATTERN_003": profile},
        factors=factors,
    )

    evaluation = scorer.score(
        pattern_result("PATTERN_003"),
        bars_from_centers([10, 12, 11, 14, 12]),
    )

    assert evaluation.composite.score == 57.5
    assert evaluation.composite.metadata["effective_scores"] == {
        "Positive": 50.0,
        "Negative": 20.0,
    }
