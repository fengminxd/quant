"""Configuration for the isolated Telegram notification subsystem."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NOTIFICATION_TIMEFRAMES = ("1h", "4h")
HISTORY_BARS = 201


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram Bot API credentials and delivery settings."""

    token: str
    chat_id: str
    retries: int = 3
    timeout_seconds: float = 20.0


@dataclass(frozen=True)
class NotificationConfig:
    """Runtime settings that do not alter the central trading policy."""

    telegram: TelegramConfig
    state_db: Path = Path("logs/notifications/state.sqlite3")
    scan_delay_seconds: float = 5.0
    heartbeat_interval_seconds: float = 300.0
    bootstrap_retry_seconds: float = 30.0
    delivery_retry_interval_seconds: float = 10.0
    data_lag_alert_bars: int = 1
    max_restart_replay_bars: int = 1_000


def load_notification_config(
    path: str | Path = "config/notifications.json",
) -> NotificationConfig:
    """Load Telegram settings, resolving secrets from environment variables."""

    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)
    telegram = _mapping(payload.get("telegram"), "telegram")
    token = _secret(telegram, "token", "token_env")
    chat_id = _secret(telegram, "chat_id", "chat_id_env")
    if not token or not chat_id:
        raise ValueError("Telegram token and chat_id must be configured")
    retries = int(telegram.get("retries", 3))
    timeout = float(telegram.get("timeout_seconds", 20.0))
    if retries <= 0 or timeout <= 0:
        raise ValueError("Telegram retries and timeout_seconds must be positive")
    intervals = {
        "heartbeat_interval_seconds": float(
            payload.get("heartbeat_interval_seconds", 300.0)
        ),
        "bootstrap_retry_seconds": float(
            payload.get("bootstrap_retry_seconds", 30.0)
        ),
        "delivery_retry_interval_seconds": float(
            payload.get("delivery_retry_interval_seconds", 10.0)
        ),
    }
    if any(value <= 0 for value in intervals.values()):
        raise ValueError("notification service intervals must be positive")
    scan_delay = float(payload.get("scan_delay_seconds", 5.0))
    if not 5 <= scan_delay <= 10:
        raise ValueError("scan_delay_seconds must be between 5 and 10")
    lag_bars = int(payload.get("data_lag_alert_bars", 1))
    replay_bars = int(payload.get("max_restart_replay_bars", 1_000))
    if lag_bars <= 0 or replay_bars <= 0:
        raise ValueError("lag and restart replay bar limits must be positive")
    return NotificationConfig(
        telegram=TelegramConfig(token, chat_id, retries, timeout),
        state_db=Path(str(payload.get("state_db", "logs/notifications/state.sqlite3"))),
        scan_delay_seconds=scan_delay,
        **intervals,
        data_lag_alert_bars=lag_bars,
        max_restart_replay_bars=replay_bars,
    )


def _secret(payload: dict[str, Any], value_key: str, env_key: str) -> str:
    literal = str(payload.get(value_key, "")).strip()
    if literal:
        return literal
    env_name = str(payload.get(env_key, "")).strip()
    return os.environ.get(env_name, "").strip() if env_name else ""


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value
