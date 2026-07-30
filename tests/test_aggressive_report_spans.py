from __future__ import annotations

from research.aggressive_trade_report import _anchor_span_fields
from tests.test_aggressive_trade_report import bars, event


def test_pattern_003_report_fields_include_each_anchor_span() -> None:
    source = bars()

    fields = _anchor_span_fields(event(source, pattern_id="PATTERN_003"))

    assert fields == (
        "p1_p2_span_bars=1 "
        "p2_p3_span_bars=2 "
        "p1_p3_span_bars=3 "
    )


def test_non_three_point_pattern_has_no_anchor_span_fields() -> None:
    source = bars()

    assert _anchor_span_fields(event(source, pattern_id="PATTERN_004")) == ""
