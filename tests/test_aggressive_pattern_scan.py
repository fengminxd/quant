from __future__ import annotations

from collections.abc import Callable

import pytest

from backtest.aggressive_entries import aggressive_entry_definition
from core.models import Bar
from research.aggressive_pattern_scan import AggressivePatternScanner
from research.pattern_events import PatternAnchor, PatternScanEvent
from tests.test_aggressive_trade_report import bars, event
from tests.test_btc_1h_double_bottom_support import (
    CONFIRMED_AT,
    RIGHT_ANCHOR,
    btc_bars,
)
from tests.test_causal_anchor_entries import trend_bars
from tests.test_head_shoulders_top import top_bars
from tests.test_inverse_head_shoulders import pattern_bars


@pytest.mark.parametrize(
    ("pattern_id", "count", "position", "direction"),
    [
        ("PATTERN_004", 2, 1, "bullish"),
        ("PATTERN_006", 2, 1, "bearish"),
        ("PATTERN_007", 3, 2, "bullish"),
        ("PATTERN_008", 3, 2, "bearish"),
        ("PATTERN_003", 3, 2, "bullish"),
    ],
)
def test_requested_pattern_anchor_mapping(
    pattern_id: str,
    count: int,
    position: int,
    direction: str,
) -> None:
    source = bars()
    scan_event = event(source, pattern_id=pattern_id)

    definition = aggressive_entry_definition(scan_event, source)

    assert definition is not None
    assert len(scan_event.anchors) == count
    assert definition.anchor == scan_event.anchors[position]
    assert definition.direction == direction


@pytest.mark.parametrize(
    ("trend", "upper_indexes", "lower_indexes", "expected", "direction"),
    [
        (1, (115, 135), (110, 125, 140), 140, "bullish"),
        (-1, (115, 130, 145), (110, 140), 145, "bearish"),
    ],
)
def test_triangle_uses_frozen_trend_and_directional_boundary_p3(
    trend: int,
    upper_indexes: tuple[int, ...],
    lower_indexes: tuple[int, ...],
    expected: int,
    direction: str,
) -> None:
    source = trend_bars(trend)
    upper = tuple(
        PatternAnchor(index, source[index].timestamp, source[index].high)
        for index in upper_indexes
    )
    lower = tuple(
        PatternAnchor(index, source[index].timestamp, source[index].low)
        for index in lower_indexes
    )
    scan_event = PatternScanEvent(
        "BTC",
        "1h",
        "PATTERN_002",
        "Triangle",
        "triangle",
        80.0,
        source[expected].timestamp,
        tuple(sorted((*upper, *lower), key=lambda anchor: anchor.index)),
        (upper, lower),
    )

    definition = aggressive_entry_definition(scan_event, source)

    assert definition is not None
    assert definition.anchor.index == expected
    assert definition.direction == direction


def test_scanner_waits_five_right_bars_to_confirm_support_anchor() -> None:
    source = btc_bars()

    before = AggressivePatternScanner().scan("BTC", "1h", source[:142])
    events = AggressivePatternScanner().scan("BTC", "1h", source)
    premature = [
        item
        for item in before
        if item.pattern_id == "PATTERN_004"
        and item.anchors[-1].timestamp == RIGHT_ANCHOR
    ]
    matching = [
        item
        for item in events
        if item.pattern_id == "PATTERN_004"
        and item.anchors[-1].timestamp == RIGHT_ANCHOR
    ]

    assert premature == []
    assert len(matching) == 1
    assert matching[0].anchors[-1].index == 137
    assert matching[0].detected_timestamp == CONFIRMED_AT


@pytest.mark.parametrize(
    ("factory", "pattern_id", "enabled"),
    [
        (pattern_bars, "PATTERN_007", True),
        (top_bars, "PATTERN_008", False),
    ],
)
def test_scanner_emits_only_enabled_right_shoulder_after_confirmation(
    factory: Callable[[], list[Bar]],
    pattern_id: str,
    enabled: bool,
) -> None:
    source = factory()

    before = AggressivePatternScanner().scan("BTC", "1h", source[:65])
    events = AggressivePatternScanner().scan("BTC", "1h", source)
    premature = [
        item
        for item in before
        if item.pattern_id == pattern_id
        and item.anchors[-1].index == 60
    ]
    matching = [
        item
        for item in events
        if item.pattern_id == pattern_id
        and item.anchors[-1].index == 60
    ]

    assert premature == []
    assert len(matching) == int(enabled)
    if enabled:
        assert matching[0].anchors[-1].index == 60
        assert matching[0].detected_timestamp == source[65].timestamp
