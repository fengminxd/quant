"""Minimal Telegram Bot API photo delivery with bounded retries."""

from __future__ import annotations

import asyncio

from notifications.config import TelegramConfig


class TelegramClient:
    """Send one candlestick PNG and caption without logging Bot credentials."""

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config

    async def send_photo(
        self,
        image: bytes,
        caption: str,
        *,
        filename: str = "pattern.png",
    ) -> None:
        """Deliver a PNG, retrying transient HTTP or Telegram failures."""

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to send Telegram notifications") from exc
        url = f"https://api.telegram.org/bot{self.config.token}/sendPhoto"
        for attempt in range(self.config.retries):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    response = await client.post(
                        url,
                        data={"chat_id": self.config.chat_id, "caption": caption},
                        files={"photo": (filename, image, "image/png")},
                    )
                payload = response.json()
                if response.is_success and payload.get("ok") is True:
                    return
            except Exception:
                pass
            if attempt + 1 < self.config.retries:
                await asyncio.sleep(2**attempt)
        raise RuntimeError("Telegram photo delivery failed after configured retries")

    async def send_message(self, text: str) -> None:
        """Deliver a health message through the same bounded retry policy."""

        await self._post_json("sendMessage", {"chat_id": self.config.chat_id, "text": text})

    async def _post_json(self, method: str, payload: dict[str, str]) -> None:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("install httpx to send Telegram notifications") from exc
        url = f"https://api.telegram.org/bot{self.config.token}/{method}"
        for attempt in range(self.config.retries):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    response = await client.post(url, json=payload)
                body = response.json()
                if response.is_success and body.get("ok") is True:
                    return
            except Exception:
                pass
            if attempt + 1 < self.config.retries:
                await asyncio.sleep(2**attempt)
        raise RuntimeError("Telegram message delivery failed after configured retries")
