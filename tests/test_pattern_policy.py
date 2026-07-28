from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backtest.aggressive_anchor_strategy import AggressiveAnchorStrategyEvaluator
from core.models import Bar, PatternResult
from core.pattern_policy import (
    ACTIVE_TRADING_PATTERN_IDS,
    COMBINATION_ONLY_PATTERN_IDS,
    DISABLED_FIXED_COMBINATION_IDS,
    DISABLED_TRADING_PATTERN_IDS,
    is_fixed_combination_enabled,
    is_pattern_analysis_enabled,
    is_trade_event_enabled,
    is_trading_pattern_enabled,
)
from factors.trade_feasibility import PatternTradeFeasibilityScorer
from features.trade_plan import PatternTradePlan, PatternTradePlanExtractor
from patterns import ThreePointTrendlineResistance, TrendlineSupport
from patterns.detector import PatternPollResult
from research.aggressive_trade_report import write_aggressive_trade_report
from research.anchor_trade_report import write_anchor_trade_report
from research.pattern_events import PatternAnchor, PatternScanEvent
from research.pattern_scan import HistoricalPatternScanner


def bars(length: int = 60) -> list[Bar]:
    return [
        Bar(
            index * 3_600_000,
            100.0,
            100.5,
            99.5,
            100.0,
            1000.0,
            "1h",
        )
        for index in range(length)
    ]


def pattern(pattern_id: str) -> PatternResult:
    return PatternResult(
        pattern_id,
        pattern_id,
        True,
        80.0,
        geometry={"points": [(0, 100.0), (40, 100.0)]},
        metadata={"detected_at_index": 40},
    )


def event(
    pattern_id: str,
    source: list[Bar],
    combination_id: str | None = None,
) -> PatternScanEvent:
    anchors = (
        PatternAnchor(0, source[0].timestamp, 100.0),
        PatternAnchor(10, source[10].timestamp, 100.0),
        PatternAnchor(20, source[20].timestamp, 100.0),
    )
    return PatternScanEvent(
        "BTC",
        "1h",
        pattern_id,
        pattern_id,
        "test_rule",
        80.0,
        source[40].timestamp,
        anchors,
        (anchors,),
        priority_fixed_combination=combination_id is not None,
        priority_combination_id=combination_id,
    )


class DisabledResultDetector:
    def poll_at(
        self,
        source: list[Bar],
        timeframe: str,
        as_of_index: int,
    ) -> list[PatternPollResult]:
        if as_of_index != 40:
            return []
        return [
            PatternPollResult(
                timeframe,
                as_of_index,
                0,
                pattern("PATTERN_005"),
            )
        ]


def test_disabled_implementations_remain_importable_but_policy_is_off() -> None:
    assert TrendlineSupport.pattern_id == "PATTERN_001"
    assert ThreePointTrendlineResistance.pattern_id == "PATTERN_005"
    assert DISABLED_TRADING_PATTERN_IDS == {
        "PATTERN_001",
        "PATTERN_005",
        "PATTERN_008",
    }
    assert COMBINATION_ONLY_PATTERN_IDS == {"PATTERN_006"}
    assert DISABLED_FIXED_COMBINATION_IDS == {"FIXED_COMBO_006"}
    assert not is_trading_pattern_enabled("PATTERN_001")
    assert not is_trading_pattern_enabled("PATTERN_005")
    assert not is_trading_pattern_enabled("PATTERN_006")
    assert not is_trading_pattern_enabled("PATTERN_008")
    assert not is_pattern_analysis_enabled("PATTERN_008")
    assert is_pattern_analysis_enabled("PATTERN_006")
    assert not is_fixed_combination_enabled("FIXED_COMBO_006")
    assert "PATTERN_003" in ACTIVE_TRADING_PATTERN_IDS
    assert "PATTERN_006" not in ACTIVE_TRADING_PATTERN_IDS


def test_pattern_006_is_tradeable_only_as_fixed_combo_002() -> None:
    assert not is_trade_event_enabled("PATTERN_006", None)
    assert is_trade_event_enabled("PATTERN_006", "FIXED_COMBO_002")
    assert not is_trade_event_enabled("PATTERN_006", "FIXED_COMBO_004")
    assert not is_trade_event_enabled("PATTERN_008", "FIXED_COMBO_004")
    assert is_trade_event_enabled("PATTERN_002", "FIXED_COMBO_008")
    assert not is_trade_event_enabled("PATTERN_005", "FIXED_COMBO_006")
    assert is_fixed_combination_enabled("FIXED_COMBO_002")
    assert is_fixed_combination_enabled("FIXED_COMBO_004")
    assert is_fixed_combination_enabled("FIXED_COMBO_008")


@pytest.mark.parametrize(
    ("pattern_id", "direction"),
    [
        ("PATTERN_001", "bullish"),
        ("PATTERN_005", "bearish"),
        ("PATTERN_008", "bearish"),
    ],
)
def test_disabled_pattern_cannot_create_trade_plan_or_feasibility(
    pattern_id: str,
    direction: str,
) -> None:
    source = bars()
    explicit = PatternTradePlan(direction, 100.0, 98.0, 104.0)
    result = pattern(pattern_id)

    plan, _, _ = PatternTradePlanExtractor().extract(
        result, source, plan=explicit
    )
    evaluation = PatternTradeFeasibilityScorer().score(
        result, source, plan=explicit
    )

    assert plan is None
    assert evaluation.plan is None
    assert evaluation.factor.metadata["pattern_enabled"] is False
    assert evaluation.factor.metadata["pattern_gate_passed"] is False
    assert evaluation.factor.metadata["active"] is False


def test_historical_scanner_drops_disabled_custom_detector_results() -> None:
    events = HistoricalPatternScanner(
        detector=DisabledResultDetector()  # type: ignore[arg-type]
    ).scan("BTC", "1h", bars(41))

    assert events == []


def test_standard_and_aggressive_reports_omit_disabled_events(
    tmp_path: Path,
) -> None:
    source = bars()
    disabled = event("PATTERN_005", source)
    disabled_top = event("PATTERN_008", source, "FIXED_COMBO_004")
    standalone = event("PATTERN_006", source)
    enabled = event("PATTERN_006", source, "FIXED_COMBO_002")
    standard_path = tmp_path / "standard.txt"
    aggressive_path = tmp_path / "aggressive.txt"

    write_anchor_trade_report(
        [disabled, disabled_top, standalone, enabled],
        {"1h": source},
        standard_path,
        source_pdf="independent scan",
    )
    start = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))
    write_aggressive_trade_report(
        [disabled, disabled_top, standalone, enabled],
        {"1h": source},
        aggressive_path,
        start=start,
        end=start + timedelta(hours=len(source) - 1),
    )

    standard = standard_path.read_text(encoding="utf-8")
    aggressive = aggressive_path.read_text(encoding="utf-8")
    assert "PATTERN_005" not in standard
    assert "PATTERN_005" not in aggressive
    assert "pattern=PATTERN_008" not in standard
    assert "pattern=PATTERN_008" not in aggressive
    assert "去重形态数: 1" in standard
    assert "时间去重后结构数: 1" in aggressive
    assert "pattern=PATTERN_006" in standard
    assert "pattern=PATTERN_006" in aggressive
    assert "combo=FIXED_COMBO_002" in standard
    assert "combo=FIXED_COMBO_002" in aggressive


@pytest.mark.parametrize("pattern_id", ["PATTERN_005", "PATTERN_008"])
def test_aggressive_evaluator_rejects_disabled_pattern_directly(
    pattern_id: str,
) -> None:
    source = bars()

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event(pattern_id, source), source
    )

    assert plan is None


def test_aggressive_evaluator_rejects_standalone_pattern_006() -> None:
    source = bars()

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event("PATTERN_006", source), source
    )

    assert plan is None
