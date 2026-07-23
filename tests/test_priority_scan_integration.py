from __future__ import annotations

from core.models import Bar, PatternResult
from factors.priority_combinations import PriorityCombinationScorer
from patterns.detector import PatternPollResult
from research.pattern_dedup import select_temporally_distinct_events
from research.pattern_scan import (
    SCAN_TIMEFRAMES,
    HistoricalPatternScanner,
    PatternAnchor,
    PatternScanEvent,
    _to_event,
    event_log_line,
)


def bars(timeframe: str = "1h", length: int = 123) -> list[Bar]:
    source = [
        Bar(index, 100.0, 101.0, 99.0, 100.0, 1000.0, timeframe)
        for index in range(length)
    ]
    source[120] = Bar(120, 100.0, 101.0, 95.0, 100.5, 1000.0, timeframe)
    return source


def support_pattern(points: list[tuple[int, float]]) -> PatternResult:
    return PatternResult(
        "PATTERN_004",
        "Horizontal Support",
        True,
        80.0,
        geometry={"points": points},
        metadata={"rule_type": "double_swing_low", "detected_at_index": 122},
    )


class FixedSupportDetector:
    def poll_at(
        self, source: list[Bar], timeframe: str, as_of_index: int
    ) -> list[PatternPollResult]:
        if as_of_index != 122:
            return []
        return [
            PatternPollResult(
                timeframe,
                as_of_index,
                0,
                support_pattern([(60, 95.0), (120, 95.0)]),
            )
        ]


def test_historical_scan_marks_and_serializes_priority_combination() -> None:
    scanner = HistoricalPatternScanner(detector=FixedSupportDetector())  # type: ignore[arg-type]

    event = scanner.scan("BTC", "1h", bars())[0]
    line = event_log_line(event)

    assert event.priority_fixed_combination is True
    assert event.priority_combination_id == "FIXED_COMBO_001"
    assert event.priority_combination_score == 100.0
    assert event.priority_level_sources == ()
    assert "priority_fixed=true" in line
    assert "FIXED_COMBO_001" in line


def test_polling_window_offset_maps_local_anchors_to_full_history_ema() -> None:
    pattern = support_pattern([(10, 95.0), (70, 95.0)])

    result = PriorityCombinationScorer().score(
        pattern,
        bars(),
        as_of_index=122,
        window_start_index=50,
    )

    evidence = result.metadata["condition_evidence"][
        "second_anchor_close_above_ema99"
    ]
    assert evidence["anchor_index"] == 120
    assert result.metadata["priority_fixed_combination"] is True


def test_scan_event_preserves_fixed_combo_level_relation() -> None:
    source = [
        Bar(index, 104.0, 105.0, 103.0, 104.0, 1000.0, "1h")
        for index in range(123)
    ]
    source[60] = Bar(60, 105.0, 106.0, 103.0, 104.0, 1000.0, "1h")
    for index in range(80, 121):
        source[index] = Bar(
            index, 106.0, 108.0, 105.5, 106.5, 1000.0, "1h"
        )
    source[120] = Bar(120, 107.0, 108.0, 105.0, 107.5, 1000.0, "1h")
    pattern = PatternResult(
        "PATTERN_003",
        "Three Point Trendline Support",
        True,
        80.0,
        geometry={"points": [(100, 105.5), (110, 105.5), (120, 105.0)]},
        metadata={"detected_at_index": 122},
    )

    event = _to_event(
        "BTC",
        source,
        PatternPollResult("1h", 122, 0, pattern),
    )

    assert event is not None
    assert len(event.priority_level_relations) == 1
    relation = event.priority_level_relations[0]
    assert relation.condition == "third_anchor_breakout_retest_support"
    assert relation.rule_type == "breakout_retest"
    assert relation.source.index == 60
    assert relation.target.index == 120


def test_priority_combinations_are_limited_to_three_trading_timeframes() -> None:
    assert SCAN_TIMEFRAMES == ("15m", "1h", "4h")

    result = PriorityCombinationScorer().score(
        support_pattern([(60, 95.0), (120, 95.0)]),
        bars("1d"),
        as_of_index=122,
    )

    assert result.metadata["priority_fixed_combination"] is False
    assert result.metadata["gate_passed"] is False


def test_nearby_dedup_preserves_priority_event_before_raw_pattern_score() -> None:
    anchors = (
        PatternAnchor(60, 60, 95.0),
        PatternAnchor(120, 120, 95.0),
    )
    ordinary = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_004",
        "Horizontal Support",
        "double_swing_low",
        99.0,
        120,
        anchors,
    )
    priority = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_004",
        "Horizontal Support",
        "double_swing_low",
        70.0,
        121,
        anchors,
        priority_fixed_combination=True,
        priority_combination_id="FIXED_COMBO_001",
        priority_combination_score=100.0,
        priority_level_sources=(PatternAnchor(40, 40, 95.0),),
    )

    selected = select_temporally_distinct_events([ordinary, priority])

    assert selected == [priority]
    assert priority.first_anchor_index == 60
    assert "level_sources=[1970-01-01 08:00:00 UTC+8]" in event_log_line(
        priority
    )
