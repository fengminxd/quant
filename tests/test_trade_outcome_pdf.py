from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtest.trade_outcome_labels import AnchorTrade, parse_anchor_trades
from core.models import Bar
from visualization.trade_outcome_pdf import write_trade_outcome_pdf


UTC_PLUS_8 = timezone(timedelta(hours=8))


def test_supplied_anchor_report_parses_all_qualified_trades() -> None:
    trades = parse_anchor_trades(
        "logs/btc_1h_pdf_explanations/pdf/BTC_1h_anchor_trade_outcomes.txt"
    )

    assert len(trades) == 85
    assert sum(trade.outcome == "take_profit" for trade in trades) == 65
    assert sum(trade.outcome == "stop_loss" for trade in trades) == 14
    unresolved = [trade for trade in trades if trade.outcome == "unresolved"]
    assert len(unresolved) == 6
    assert all(trade.exit_time is None for trade in unresolved)


def test_trade_pdf_contains_summary_and_adjacent_chart_pages(tmp_path) -> None:
    start = datetime(2026, 4, 20, 8, tzinfo=UTC_PLUS_8)
    bars = [
        Bar(
            timestamp=int((start + timedelta(hours=index)).timestamp() * 1000),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=10,
            timeframe="1h",
        )
        for index in range(3)
    ]
    trade = AnchorTrade(
        trade_id=1,
        pattern="PATTERN_004",
        rule="double_swing_low",
        outcome="take_profit",
        direction="bullish",
        entry_time=start,
        entry=100,
        stop=98.5,
        target=101.5,
        exit_time=start + timedelta(hours=1),
    )
    output = tmp_path / "trades.pdf"

    write_trade_outcome_pdf(
        "BTC",
        "1h",
        bars,
        [trade],
        output,
        candles_per_page=2,
    )

    payload = output.read_bytes()
    assert payload.startswith(b"%PDF")
    assert b"/Count 3" in payload


def test_new_profit_lock_fields_parse_without_breaking_old_reports(
    tmp_path: Path,
) -> None:
    report = tmp_path / "profit_lock.txt"
    report.write_text(
        "symbol=BTC timeframe=1h pattern=PATTERN_004 rule=test "
        "outcome=protected_profit combo=- conditions=[-] direction=bullish "
        "entry_rule='retest' structure_time=2026-06-30 20:00:00 UTC+8 "
        "structure_level=99.50000000 "
        "entry_time=2026-07-01 08:00:00 UTC+8 "
        "entry=100.00000000 stop=98.50000000 target=103.00000000 "
        "lock_trigger=101.50000000 locked_stop=101.50000000 "
        "lock_time=2026-07-01 09:00:00 UTC+8 "
        "exit_time=2026-07-01 10:00:00 UTC+8 exit=101.50000000 "
        "bars_held=2\n",
        encoding="utf-8",
    )

    trade = parse_anchor_trades(report)[0]

    assert trade.outcome == "protected_profit"
    assert trade.lock_trigger == 101.5
    assert trade.locked_stop == 101.5
    assert trade.exit_price == 101.5
    assert trade.lock_time == datetime(2026, 7, 1, 9, tzinfo=UTC_PLUS_8)
