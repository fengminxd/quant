from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from core.base import Pattern
from core.models import Bar, FeatureResult, PatternResult
from core.timeframes import (
    StructureSpanStatus,
    TimeframeRole,
    resolve_structure_span,
    timeframe_level,
)
from data.market_config import MarketDataConfig, SymbolConfig
from patterns.detector import PatternDetector


def make_bars(timeframe: str, count: int) -> list[Bar]:
    """Build valid bars whose timestamp exposes the visible polling boundary."""

    return [Bar(index, 10.0, 11.0, 9.0, 10.5, 100.0, timeframe) for index in range(count)]


class RecordingPattern(Pattern):
    """Test pattern recording every window supplied by the polling layer."""

    def __init__(self, span: int | None = None) -> None:
        self.windows: list[Sequence[Bar]] = []
        self.span = span

    def detect(self, data: Sequence[Bar]) -> PatternResult:
        self.windows.append(data)
        span = self.span if self.span is not None else len(data) - 1
        return PatternResult(
            "TEST",
            "Recording Pattern",
            True,
            50.0,
            {"span": FeatureResult("span", float(span), 1.0)},
        )

    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        return {"span": FeatureResult("span", float(len(data) - 1), 1.0)}

    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        return 50.0

    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        return result.geometry


@pytest.mark.parametrize(
    ("timeframe", "span", "resolved_timeframe", "resolved_span", "status", "promotions"),
    [
        ("15m", 39, "15m", 39, StructureSpanStatus.BELOW_MINIMUM, 0),
        ("15m", 40, "15m", 40, StructureSpanStatus.TRADING, 0),
        ("15m", 160, "15m", 160, StructureSpanStatus.TRADING, 0),
        ("15m", 161, "1h", 41, StructureSpanStatus.TRADING, 1),
        ("15m", 640, "1h", 160, StructureSpanStatus.TRADING, 1),
        ("15m", 641, "4h", 41, StructureSpanStatus.TRADING, 2),
        ("1h", 161, "4h", 41, StructureSpanStatus.TRADING, 1),
        ("4h", 160, "4h", 160, StructureSpanStatus.TRADING, 0),
        ("4h", 161, "1d", 27, StructureSpanStatus.TREND_ONLY, 1),
        ("1d", 100, "1d", 100, StructureSpanStatus.TREND_ONLY, 0),
    ],
)
def test_resolve_structure_span_boundaries(
    timeframe: str,
    span: int,
    resolved_timeframe: str,
    resolved_span: int,
    status: StructureSpanStatus,
    promotions: int,
) -> None:
    resolution = resolve_structure_span(timeframe, span)

    assert resolution.timeframe == resolved_timeframe
    assert resolution.span_bars == resolved_span
    assert resolution.status is status
    assert resolution.promotions == promotions


def test_daily_is_trend_context_and_not_tradable() -> None:
    assert timeframe_level("1d").role is TimeframeRole.TREND_CONTEXT
    assert resolve_structure_span("1d", 100).is_tradable is False


def test_market_data_config_separates_trading_and_trend_levels() -> None:
    config = MarketDataConfig(
        (SymbolConfig("BTC", "BTCUSDT"),),
        ("15m", "1h", "4h", "1d"),
        2_000,
    )

    assert config.trading_timeframes == ("15m", "1h", "4h")
    assert config.trend_timeframes == ("1d",)


def test_poll_uses_three_levels_and_caps_each_visible_window() -> None:
    pattern = RecordingPattern()
    detector = PatternDetector([pattern])
    bars = {
        "15m": make_bars("15m", 200),
        "1h": make_bars("1h", 100),
        "4h": make_bars("4h", 41),
        "1d": make_bars("1d", 200),
    }

    results = detector.poll(bars)

    assert [len(window) for window in pattern.windows] == [161, 100, 41]
    assert [result.timeframe for result in results] == ["15m", "1h", "4h"]
    assert [result.window_start_index for result in results] == [39, 0, 0]
    assert all(result.pattern.metadata["timeframe_role"] == "trading" for result in results)


def test_poll_at_never_reads_bars_after_as_of_index() -> None:
    pattern = RecordingPattern(span=40)
    detector = PatternDetector([pattern])
    data = make_bars("15m", 250)

    result = detector.poll_at(data, "15m", 190)

    assert len(pattern.windows) == 1
    assert len(pattern.windows[0]) == 161
    assert pattern.windows[0][-1].timestamp == 190
    assert result[0].window_start_index == 30
    assert result[0].pattern.metadata["as_of_index"] == 190


def test_poll_rejects_structures_outside_40_to_160_bars() -> None:
    short = PatternDetector([RecordingPattern(span=39)])
    long = PatternDetector([RecordingPattern(span=161)])
    data = make_bars("1h", 200)

    assert short.poll_at(data, "1h", 199) == []
    assert long.poll_at(data, "1h", 199) == []


def test_daily_bars_never_enter_pattern_polling() -> None:
    pattern = RecordingPattern(span=40)
    detector = PatternDetector([pattern])

    assert detector.poll_at(make_bars("1d", 200), "1d", 199) == []
    assert pattern.windows == []


def test_poll_rejects_mixed_timeframe_bars_before_as_of() -> None:
    data = make_bars("15m", 50)
    data[20] = Bar(20, 10.0, 11.0, 9.0, 10.5, 100.0, "1h")

    with pytest.raises(ValueError, match="does not match"):
        PatternDetector([RecordingPattern()]).poll_at(data, "15m", 49)


@pytest.mark.parametrize("span", [-1, 1.5, True])
def test_structure_span_rejects_invalid_values(span: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        resolve_structure_span("15m", span)  # type: ignore[arg-type]
