"""CLI entry point for real-time Telegram Pattern notifications."""

from __future__ import annotations

import argparse
import asyncio
import logging

from data.market_config import load_market_data_config
from notifications.config import load_notification_config
from notifications.service import RealtimeNotificationService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan 201 closed 1h/4h candles and notify Telegram"
    )
    parser.add_argument(
        "--notifications-config",
        default="config/notifications.json",
    )
    parser.add_argument(
        "--symbols-config",
        default="config/symbols.json",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    service = RealtimeNotificationService(
        load_notification_config(args.notifications_config),
        load_market_data_config(args.symbols_config),
    )
    try:
        asyncio.run(service.run_forever())
    except KeyboardInterrupt:
        logging.info("notification service stopped")


if __name__ == "__main__":
    main()
