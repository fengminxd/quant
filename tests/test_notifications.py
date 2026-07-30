from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from core.models import Bar, FeatureResult, PatternResult
from core.pattern_policy import (
    DISABLED_FIXED_COMBINATION_IDS,
    DISABLED_TRADING_PATTERN_IDS,
)
from data.market_config import MarketDataConfig
from features.priority_profiles import PriorityCombinationFeatureSet
from notifications.chart import render_notification_chart
from notifications.config import (
    HISTORY_BARS,
    NotificationConfig,
    TelegramConfig,
    load_notification_config,
)
from notifications.event_store import NotificationEventStore
from notifications.formatter import telegram_caption
from notifications.scanner import (
    NotificationPatternScanner,
    NotificationPriorityScorer,
)
from notifications.service import RealtimeNotificationService
from tests.test_head_shoulders_top import top_bars
from tests.test_btc_1h_double_bottom_support import btc_bars
from tests.test_horizontal_resistance import resistance_bars as horizontal_resistance_bars
from tests.test_inverse_head_shoulders import pattern_bars
from tests.test_near_4h_triangle import near_bars
from tests.test_three_point_trendline_resistance import (
    resistance_bars as trendline_resistance_bars,
)
from tests.test_three_point_trendline_support import hype_support_bars


def pad_to_window(visible: list[Bar]) -> list[Bar]:
    """Shift one fixture's right-edge anchor onto candle 201."""

    prefix = [visible[0]] * (HISTORY_BARS - len(visible))
    return [*prefix, *visible]


def notification_window(source: list[Bar]) -> list[Bar]:
    return pad_to_window(source[:61])


def test_config_resolves_telegram_secrets_from_environment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "notifications.json"
    path.write_text(
        json.dumps(
            {
                "telegram": {
                    "token_env": "TEST_TELEGRAM_TOKEN",
                    "chat_id_env": "TEST_TELEGRAM_CHAT",
                },
                "state_db": str(tmp_path / "state.sqlite3"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_TELEGRAM_TOKEN", "secret-token")
    monkeypatch.setenv("TEST_TELEGRAM_CHAT", "-100123")

    config = load_notification_config(path)

    assert config.telegram.token == "secret-token"
    assert config.telegram.chat_id == "-100123"
    assert config.state_db == tmp_path / "state.sqlite3"
    invalid = json.loads(path.read_text(encoding="utf-8"))
    invalid["scan_delay_seconds"] = 0
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="between 5 and 10"):
        load_notification_config(path)


def test_notification_scanner_enables_unconfirmed_pattern_008_only_locally() -> None:
    bars = notification_window(top_bars())

    matches = NotificationPatternScanner().scan("TEST", "1h", bars)
    top = next(match for match in matches if match.pattern.pattern_id == "PATTERN_008")

    assert top.anchors[2].label == "RS"
    assert top.anchors[2].index == HISTORY_BARS - 1
    assert "PATTERN_008" in DISABLED_TRADING_PATTERN_IDS


def test_notification_scanner_accepts_unconfirmed_pattern_007_right_shoulder() -> None:
    bars = notification_window(pattern_bars(timeframe="4h"))

    matches = NotificationPatternScanner().scan("TEST", "4h", bars)

    inverse = next(
        match for match in matches if match.pattern.pattern_id == "PATTERN_007"
    )
    assert inverse.anchors[2].index == HISTORY_BARS - 1
    assert inverse.detected_timestamp == bars[-1].timestamp


def test_notification_scanner_requires_exactly_201_bars() -> None:
    with pytest.raises(ValueError, match="exactly 201"):
        NotificationPatternScanner().scan("TEST", "1h", pattern_bars())


@pytest.mark.parametrize(
    ("pattern_id", "timeframe", "visible"),
    [
        ("PATTERN_002", "4h", near_bars()),
        (
            "PATTERN_003",
            "1h",
            [replace(bar, timeframe="1h") for bar in hype_support_bars()[:93]],
        ),
        ("PATTERN_004", "1h", btc_bars()[:138]),
        ("PATTERN_005", "1h", trendline_resistance_bars()[:71]),
        ("PATTERN_006", "1h", horizontal_resistance_bars()[:46]),
    ],
)
def test_notification_scanner_covers_pattern_002_through_006_at_right_edge(
    pattern_id: str,
    timeframe: str,
    visible: list[Bar],
) -> None:
    bars = pad_to_window(visible)

    matches = NotificationPatternScanner().scan("TEST", timeframe, bars)
    match = next(item for item in matches if item.pattern.pattern_id == pattern_id)

    assert any(anchor.index == HISTORY_BARS - 1 for anchor in match.anchors)


class _Combo006Extractor:
    def extract(self, *args, **kwargs) -> PriorityCombinationFeatureSet:
        names = (
            "pattern_gate",
            "timeframe_gate",
            "variant_gate",
            "trend_gate",
            "first_anchor_horizontal_resistance",
            "third_anchor_open_below_ema99",
        )
        features = {
            name: FeatureResult(name, 1.0, 1.0)
            for name in names
        }
        return PriorityCombinationFeatureSet(
            "FIXED_COMBO_006",
            "notification-only resistance combination",
            names[-2:],
            features,
        )


def test_notification_priority_scorer_can_evaluate_disabled_combo_006() -> None:
    pattern = PatternResult("PATTERN_005", "Resistance", True, 80.0)
    bars = notification_window(pattern_bars())

    result = NotificationPriorityScorer(
        extractor=_Combo006Extractor()  # type: ignore[arg-type]
    ).score(pattern, bars)

    assert result is not None
    assert result.metadata["active"] is True
    assert result.metadata["combination_id"] == "FIXED_COMBO_006"
    assert "FIXED_COMBO_006" in DISABLED_FIXED_COMBINATION_IDS


def test_chart_and_caption_include_required_notification_information() -> None:
    bars = notification_window(top_bars())
    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", "1h", bars)
        if item.pattern.pattern_id == "PATTERN_008"
    )

    image = render_notification_chart(match, bars)
    caption = telegram_caption(match, bars)

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) > 10_000
    assert "symbol: TEST" in caption
    assert "PATTERN_008" in caption
    assert "周期: 1h" in caption
    assert "UTC+8" in caption
    assert "FIXED_COMBO:" in caption


def test_event_store_deduplicates_across_reopen(tmp_path) -> None:
    bars = notification_window(pattern_bars())
    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", "1h", bars)
        if item.pattern.pattern_id == "PATTERN_007"
    )
    path = tmp_path / "state.sqlite3"
    first = NotificationEventStore(path)
    assert first.contains(match.identity) is False
    first.mark_sent(match)
    first.close()

    reopened = NotificationEventStore(path)
    assert reopened.contains(match.identity) is True
    reopened.close()


def test_event_store_persists_payload_until_delivery(tmp_path) -> None:
    bars = notification_window(pattern_bars())
    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", "1h", bars)
        if item.pattern.pattern_id == "PATTERN_007"
    )
    path = tmp_path / "outbox.sqlite3"
    first = NotificationEventStore(path)
    first.enqueue(
        match,
        filename="pattern.png",
        caption="caption",
        image=b"png",
    )
    first.close()

    reopened = NotificationEventStore(path)
    pending = reopened.pending()
    assert len(pending) == 1
    assert pending[0].identity == match.identity
    assert pending[0].image == b"png"
    reopened.mark_pending_sent(pending[0])
    assert reopened.pending() == []
    assert reopened.contains(match.identity) is True
    reopened.close()


class _TelegramRecorder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[bytes, str, str]] = []

    async def send_photo(
        self,
        image: bytes,
        caption: str,
        *,
        filename: str,
    ) -> None:
        self.calls.append((image, caption, filename))
        if self.fail:
            raise RuntimeError("offline")


@pytest.mark.parametrize("fail", [False, True])
def test_service_delivers_or_retains_durable_outbox(tmp_path, fail: bool) -> None:
    bars = notification_window(pattern_bars())
    match = next(
        item
        for item in NotificationPatternScanner().scan("TEST", "1h", bars)
        if item.pattern.pattern_id == "PATTERN_007"
    )
    store = NotificationEventStore(tmp_path / "service.sqlite3")
    store.enqueue(match, filename="pattern.png", caption="caption", image=b"png")
    telegram = _TelegramRecorder(fail)
    config = NotificationConfig(
        TelegramConfig("token", "chat"),
        state_db=tmp_path / "unused.sqlite3",
    )
    service = RealtimeNotificationService(
        config,
        MarketDataConfig((), ("1h", "4h"), HISTORY_BARS),
        telegram=telegram,  # type: ignore[arg-type]
        event_store=store,
    )

    asyncio.run(service._deliver_pending())

    assert len(telegram.calls) == 1
    assert len(store.pending()) == int(fail)
    assert store.contains(match.identity) is True
    store.close()
