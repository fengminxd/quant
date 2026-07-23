from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.models import Bar, PatternResult
from patterns.detector import PatternDetector, PatternPollResult
from research.pattern_dedup import select_temporally_distinct_events
from research.pattern_scan import (
    HistoricalPatternScanner,
    PatternAnchor,
    PatternScanEvent,
    PriorityLevelRelation,
    candles_to_bars,
    event_log_line,
    scan_patterns,
)
from visualization.pattern_pdf import _draw_event, write_symbol_pdf
from visualization.pattern_text import level_relation_kind
import matplotlib.pyplot as plt


def make_bars(length: int = 41, timeframe: str = "1h") -> list[Bar]:
    return [
        Bar(
            timestamp=index * 3_600_000,
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0,
            timeframe=timeframe,
        )
        for index in range(length)
    ]


class RepeatingDetector:
    def poll_at(
        self,
        bars: list[Bar],
        timeframe: str,
        as_of_index: int,
    ) -> list[PatternPollResult]:
        if as_of_index not in (40, 41):
            return []
        result = PatternResult(
            "PATTERN_006",
            "Horizontal Resistance",
            True,
            88.0,
            geometry={"points": [(0, 101.0), (40, 141.0)]},
            metadata={
                "rule": "strict_two_swing_horizontal_resistance",
                "detected_at_index": 40,
            },
        )
        return [PatternPollResult(timeframe, as_of_index, 0, result)]


def test_scan_registry_contains_002_through_008_only() -> None:
    ids = [pattern.pattern_id for pattern in scan_patterns()]

    assert ids == [f"PATTERN_{number:03d}" for number in range(2, 9)]


def test_historical_scanner_deduplicates_identical_anchors() -> None:
    bars = make_bars(42)
    scanner = HistoricalPatternScanner(detector=RepeatingDetector())  # type: ignore[arg-type]

    events = scanner.scan("BTC", "1h", bars)

    assert len(events) == 1
    assert [anchor.index for anchor in events[0].anchors] == [0, 40]


def test_event_driven_scan_matches_full_polling_on_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "btc_4h_three_point_resistance.json"
    rows = json.loads(fixture.read_text(encoding="utf-8"))
    bars = [Bar(row[0], *row[1:], "4h") for row in rows]

    event_driven = HistoricalPatternScanner().scan("BTC", "4h", bars)
    full_polling = HistoricalPatternScanner(PatternDetector(scan_patterns())).scan(
        "BTC", "4h", bars
    )

    assert {event.identity for event in event_driven} == {
        event.identity for event in full_polling
    }


def test_log_line_formats_anchor_times_as_utc_plus_8() -> None:
    event = PatternScanEvent(
        symbol="BTC",
        timeframe="1h",
        pattern_id="PATTERN_006",
        pattern_name="Horizontal Resistance",
        rule="strict_two_swing_horizontal_resistance",
        score=88.0,
        detected_timestamp=36_000_000,
        anchors=(PatternAnchor(0, 0, 100.0), PatternAnchor(40, 36_000_000, 101.0)),
    )

    line = event_log_line(event)

    assert "symbol=BTC timeframe=1h pattern=PATTERN_006" in line
    assert "1970-01-01 08:00:00 UTC+8" in line
    assert "1970-01-01 18:00:00 UTC+8" in line


def test_candles_to_bars_rejects_internal_gap() -> None:
    from data.candles import Candle

    first = Candle("BTC", "BTCUSDT", "15m", 0, 899_999, 1, 2, 0.5, 1.5, 10)
    third = Candle("BTC", "BTCUSDT", "15m", 1_800_000, 2_699_999, 1, 2, 0.5, 1.5, 10)

    with pytest.raises(ValueError, match="non-continuous"):
        candles_to_bars([first, third], "15m")


def test_symbol_report_is_a_pdf(tmp_path: Path) -> None:
    bars = make_bars()
    event = PatternScanEvent(
        symbol="BTC",
        timeframe="1h",
        pattern_id="PATTERN_006",
        pattern_name="Horizontal Resistance",
        rule="strict_two_swing_horizontal_resistance",
        score=88.0,
        detected_timestamp=bars[-1].timestamp,
        anchors=(
            PatternAnchor(0, bars[0].timestamp, bars[0].high),
            PatternAnchor(40, bars[40].timestamp, bars[40].high),
        ),
    )
    output = tmp_path / "BTC.pdf"

    write_symbol_pdf("BTC", {"1h": bars, "4h": ()}, [event], output)

    assert output.read_bytes().startswith(b"%PDF")


def test_temporal_dedup_keeps_best_nearby_same_rule_event() -> None:
    bars = make_bars()
    base = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_006",
        "Horizontal Resistance",
        "strict_two_swing_horizontal_resistance",
        70.0,
        bars[20].timestamp,
        (PatternAnchor(0, bars[0].timestamp, 101.0), PatternAnchor(20, bars[20].timestamp, 121.0)),
    )
    stronger = replace(base, score=90.0, detected_timestamp=bars[30].timestamp)
    later = replace(base, score=80.0, detected_timestamp=bars[40].timestamp + 20 * 3_600_000)
    other_rule = replace(base, pattern_id="PATTERN_005", rule="trendline_resistance")

    selected = select_temporally_distinct_events(
        [base, stronger, later, other_rule], nearby_hours=24.0
    )

    assert stronger in selected
    assert base not in selected
    assert later in selected
    assert other_rule in selected


def test_pdf_draws_each_anchor_group_as_a_line() -> None:
    bars = make_bars()
    upper = (
        PatternAnchor(0, bars[0].timestamp, 101.0),
        PatternAnchor(40, bars[40].timestamp, 141.0),
    )
    lower = (
        PatternAnchor(10, bars[10].timestamp, 109.0),
        PatternAnchor(30, bars[30].timestamp, 129.0),
    )
    event = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_002",
        "Triangle",
        "symmetrical_triangle",
        88.0,
        bars[-1].timestamp,
        tuple(sorted((*upper, *lower), key=lambda anchor: anchor.index)),
        (upper, lower),
    )
    figure, axis = plt.subplots()

    _draw_event(axis, bars, event)

    pattern_lines = [line for line in axis.lines if line.get_label() != "EMA99"]
    assert len(pattern_lines) == 2
    assert len([line for line in axis.lines if line.get_label() == "EMA99"]) == 1
    title = axis.get_title(loc="left")
    assert "Symbol: BTC | Timeframe: 1h" in title
    assert "Rule: PATTERN_002 / symmetrical_triangle" in title
    assert all("UTC+8" in label.get_text() for label in axis.texts)
    plt.close(figure)


def test_fixed_combo_pdf_explains_conditions_and_draws_level_evidence() -> None:
    bars = make_bars(130)
    source = PatternAnchor(40, bars[40].timestamp, 140.0)
    target = PatternAnchor(100, bars[100].timestamp, 140.0)
    anchors = (
        target,
        PatternAnchor(110, bars[110].timestamp, 150.0),
        PatternAnchor(120, bars[120].timestamp, 160.0),
    )
    relation = PriorityLevelRelation(
        "first_anchor_double_bottom_support",
        "double_swing_low",
        source,
        target,
        140.0,
    )
    event = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_003",
        "Three Point Trendline Support",
        "three_point_trendline_support",
        88.0,
        bars[122].timestamp,
        anchors,
        priority_fixed_combination=True,
        priority_combination_id="FIXED_COMBO_005",
        priority_combination_score=66.6667,
        priority_matched_conditions=(
            "first_anchor_double_bottom_support",
            "all_three_anchors_close_above_ema99",
        ),
        priority_level_relations=(relation,),
    )
    figure, axis = plt.subplots()

    _draw_event(axis, bars, event)

    title = axis.get_title(loc="left")
    assert "Fixed combination: FIXED_COMBO_005" in title
    assert "Combined conditions (2):" in title
    assert "P1 + prior anchor = double-bottom support" in title
    assert "P1/P2/P3 closes > EMA99" in title
    assert any(
        text.get_text().startswith("S1: double-bottom support")
        for text in axis.texts
    )
    assert any(
        line.get_label() == "Combo double-bottom support"
        for line in axis.lines
    )
    ema_line = next(line for line in axis.lines if line.get_label() == "EMA99")
    assert len(ema_line.get_ydata()) == 81
    plt.close(figure)


def test_pdf_classifies_strict_horizontal_resistance_as_pressure() -> None:
    prefix, label, color = level_relation_kind(
        "strict_two_swing_horizontal_resistance"
    )

    assert (prefix, label, color) == (
        "R",
        "horizontal resistance",
        "#c62828",
    )
