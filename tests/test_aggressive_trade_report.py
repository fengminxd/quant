from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backtest.aggressive_anchor_strategy import AggressiveAnchorStrategyEvaluator
from backtest.aggressive_entries import reference_order_price
from core.models import Bar
from data.candles import Candle
from features.trade_plan import TradeDirection
from research.aggressive_trade_report import write_aggressive_trade_report
from research.pattern_events import PatternAnchor, PatternScanEvent
from research.run_aggressive_trade_report import generate_aggressive_trade_report

UTC_PLUS_8 = timezone(timedelta(hours=8))


def bars(length: int = 12) -> list[Bar]:
    return [
        Bar(index * 3_600_000, 100.0, 100.5, 99.5, 100.0, 1000.0, "1h")
        for index in range(length)
    ]


def event(
    source: list[Bar],
    *,
    pattern_id: str = "PATTERN_003",
    anchor_index: int = 3,
    detected_index: int | None = None,
) -> PatternScanEvent:
    confirmation_bars = {
        "PATTERN_003": 2,
        "PATTERN_004": 5,
        "PATTERN_006": 2,
        "PATTERN_007": 5,
        "PATTERN_008": 5,
    }.get(pattern_id, 2)
    detected_index = (
        anchor_index + confirmation_bars
        if detected_index is None
        else detected_index
    )
    count = 2 if pattern_id in {"PATTERN_004", "PATTERN_006"} else 3
    anchors = tuple(
        PatternAnchor(index, source[index].timestamp, source[index].low)
        for index in range(count - 1)
    ) + (
        PatternAnchor(
            anchor_index,
            source[anchor_index].timestamp,
            source[anchor_index].low,
        ),
    )
    return PatternScanEvent(
        "BTC",
        "1h",
        pattern_id,
        pattern_id,
        "test_rule",
        80.0,
        source[detected_index].timestamp,
        anchors,
        (anchors,),
        priority_fixed_combination=pattern_id == "PATTERN_006",
        priority_combination_id=(
            "FIXED_COMBO_002" if pattern_id == "PATTERN_006" else None
        ),
    )


@pytest.mark.parametrize(
    ("pattern_id", "reference", "expected_price", "expected_source"),
    [
        (
            "PATTERN_004",
            (100.0, 102.0, 99.5, 101.0),
            99.5,
            "lower_shadow_not_longer_low",
        ),
        (
            "PATTERN_004",
            (100.0, 102.0, 98.5, 101.0),
            100.0,
            "lower_shadow_long_bullish_open",
        ),
        (
            "PATTERN_006",
            (100.0, 101.5, 99.0, 101.0),
            101.5,
            "upper_shadow_not_longer_high",
        ),
        (
            "PATTERN_006",
            (100.0, 102.5, 99.0, 101.0),
            101.0,
            "upper_shadow_long_bullish_close",
        ),
        # An exact shadow/body tie uses the entry-side extreme.
        (
            "PATTERN_004",
            (100.0, 102.0, 99.0, 101.0),
            99.0,
            "lower_shadow_not_longer_low",
        ),
        (
            "PATTERN_006",
            (100.0, 102.0, 99.0, 101.0),
            102.0,
            "upper_shadow_not_longer_high",
        ),
    ],
)
def test_reference_shadow_geometry_and_first_later_fill(
    pattern_id: str,
    reference: tuple[float, float, float, float],
    expected_price: float,
    expected_source: str,
) -> None:
    source = bars()
    source[3] = Bar(
        source[3].timestamp, *reference, 1000.0, "1h"
    )
    confirmation_index = 8 if pattern_id == "PATTERN_004" else 5
    fill_index = confirmation_index + 1
    source[fill_index] = Bar(
        source[fill_index].timestamp,
        expected_price,
        expected_price + 0.2,
        expected_price - 0.2,
        expected_price,
        1000.0,
        "1h",
    )

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event(source, pattern_id=pattern_id), source
    )

    assert plan is not None
    assert plan.structure_anchor.index == 3
    assert plan.detected_index == confirmation_index
    assert plan.entry_anchor.index == fill_index
    assert plan.entry_price == expected_price
    assert plan.reference_price_source == expected_source
    assert plan.entry_wait_bars == 1
    assert plan.confirmation_delay_bars == confirmation_index - 3
    assert plan.causal_at_entry is True


@pytest.mark.parametrize(
    ("direction", "reference", "expected"),
    [
        ("bullish", (101.0, 102.0, 99.5, 100.0), (99.5, "lower_shadow_not_longer_low")),
        (
            "bullish",
            (100.0, 102.0, 98.5, 101.0),
            (100.0, "lower_shadow_long_bullish_open"),
        ),
        (
            "bullish",
            (101.0, 102.0, 98.5, 100.0),
            (100.0, "lower_shadow_long_bearish_close"),
        ),
        ("bearish", (101.0, 101.5, 99.0, 100.0), (101.5, "upper_shadow_not_longer_high")),
        (
            "bearish",
            (100.0, 102.5, 99.0, 101.0),
            (101.0, "upper_shadow_long_bullish_close"),
        ),
        (
            "bearish",
            (101.0, 102.5, 99.0, 100.0),
            (101.0, "upper_shadow_long_bearish_open"),
        ),
    ],
)
def test_reference_shadow_rule_uses_candle_color_for_long_shadow(
    direction: TradeDirection,
    reference: tuple[float, float, float, float],
    expected: tuple[float, str],
) -> None:
    anchor = Bar(0, *reference, 1000.0, "1h")

    assert reference_order_price(anchor, direction) == expected


def test_limit_expires_after_six_closed_candles() -> None:
    source = bars(16)
    source[3] = Bar(source[3].timestamp, 100.0, 101.5, 99.5, 101.0, 1000.0, "1h")
    for index in range(9, 15):
        source[index] = Bar(
            source[index].timestamp, 101.2, 102.0, 100.1, 101.5, 1000.0, "1h"
        )
    source[15] = Bar(
        source[15].timestamp, 100.5, 101.0, 99.5, 100.0, 1000.0, "1h"
    )

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event(source, pattern_id="PATTERN_004"), source
    )

    assert plan is None


def test_anchor_close_cannot_activate_order_before_pivot_confirmation() -> None:
    source = bars()

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event(
            source,
            pattern_id="PATTERN_004",
            detected_index=3,
        ),
        source,
    )

    assert plan is None


def test_limit_may_fill_on_the_sixth_candle() -> None:
    source = bars(15)
    source[3] = Bar(source[3].timestamp, 100.0, 101.5, 99.5, 101.0, 1000.0, "1h")
    for index in range(9, 14):
        source[index] = Bar(
            source[index].timestamp, 101.2, 102.0, 100.1, 101.5, 1000.0, "1h"
        )
    source[14] = Bar(
        source[14].timestamp, 100.5, 101.0, 99.5, 100.0, 1000.0, "1h"
    )

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event(source, pattern_id="PATTERN_004"), source
    )

    assert plan is not None
    assert plan.entry_anchor.index == 14
    assert plan.entry_wait_bars == 6


@pytest.mark.parametrize(
    ("pattern_id", "direction"),
    [("PATTERN_004", "bullish"), ("PATTERN_006", "bearish")],
)
def test_doji_uses_entry_side_extreme(
    pattern_id: str,
    direction: str,
) -> None:
    source = bars()

    plan = AggressiveAnchorStrategyEvaluator().plan(
        event(source, pattern_id=pattern_id), source
    )

    assert plan is not None
    assert plan.direction == direction
    expected_price = source[3].low if direction == "bullish" else source[3].high
    expected_source = "doji_low" if direction == "bullish" else "doji_high"
    assert plan.entry_price == expected_price
    assert plan.reference_price_source == expected_source
    assert plan.entry_anchor.index == (
        9 if pattern_id == "PATTERN_004" else 6
    )


def test_fill_candle_barriers_are_ignored_and_exit_starts_next_bar() -> None:
    source = bars(12)
    source[3] = Bar(source[3].timestamp, 100.0, 101.0, 99.0, 100.5, 1000.0, "1h")
    source[9] = Bar(source[9].timestamp, 100.5, 104.0, 98.0, 100.0, 1000.0, "1h")
    source[10] = Bar(source[10].timestamp, 100.0, 103.6, 99.5, 103.0, 1000.0, "1h")

    outcome = AggressiveAnchorStrategyEvaluator().evaluate(
        event(source, pattern_id="PATTERN_004"), source
    )

    assert outcome is not None
    assert outcome.plan.entry_anchor.index == 9
    assert outcome.status == "take_profit"
    assert outcome.exit_index == 10
    assert outcome.net_return == pytest.approx(0.0289)


def test_report_describes_reference_and_delayed_fill(tmp_path: Path) -> None:
    source = bars(12)
    source[3] = Bar(source[3].timestamp, 100.0, 101.0, 99.0, 100.5, 1000.0, "1h")
    source[9] = Bar(source[9].timestamp, 100.5, 100.8, 99.8, 100.2, 1000.0, "1h")
    source[10] = Bar(source[10].timestamp, 100.2, 104.6, 99.8, 104.0, 1000.0, "1h")
    output = tmp_path / "BTC_1h_激进开单报告.txt"
    start = datetime(2026, 7, 1, 8, tzinfo=UTC_PLUS_8)

    write_aggressive_trade_report(
        [event(source, pattern_id="PATTERN_004")],
        {"1h": source},
        output,
        start=start,
        end=start + timedelta(hours=11),
        evaluator=AggressiveAnchorStrategyEvaluator(
            stop_loss_ratio=0.02,
            lock_trigger_ratio=0.02,
            take_profit_ratio=0.04,
        ),
    )

    text = output.read_text(encoding="utf-8")
    assert "必须完成右侧 Pivot Low / Pivot High 确认" in text
    assert "outcome=take_profit" in text
    assert "reference_price_source=lower_shadow_long_bullish_open" in text
    assert "confirmation_delay_bars=5" in text
    assert "entry_wait_bars=1" in text
    assert "4%止盈: 1" in text
    assert "2%保护止盈: 0" in text
    assert "达到4%止盈案例 (1)" in text


class FakeStore:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles

    async def closed_candles(
        self, symbol: str, timeframe: str, page_size: int
    ) -> list[Candle]:
        assert (symbol, timeframe, page_size) == ("BTC", "1h", 1000)
        return self.candles


def test_independent_runner_writes_distinct_report_name(tmp_path: Path) -> None:
    start = datetime(2026, 7, 1, 8, tzinfo=UTC_PLUS_8)
    candles = [
        Candle(
            "BTC",
            "BTCUSDT",
            "1h",
            round((start + timedelta(hours=index)).timestamp() * 1000),
            round((start + timedelta(hours=index + 1)).timestamp() * 1000) - 1,
            100.0,
            100.5,
            99.5,
            100.0,
            1000.0,
        )
        for index in range(41)
    ]
    end = start + timedelta(hours=40)

    result = asyncio.run(
        generate_aggressive_trade_report(
            "BTC",
            "1h",
            start,
            end,
            output_dir=tmp_path,
            store=FakeStore(candles),
            now_ms=round((end + timedelta(hours=2)).timestamp() * 1000),
        )
    )

    assert result.report_path.name == "BTC_1h_激进开单报告.txt"
    assert result.candle_count == 41
    assert result.event_count == 0
    assert result.trade_count == 0
    assert result.report_path.is_file()
