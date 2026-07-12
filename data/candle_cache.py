"""In-memory rolling candle cache."""

from __future__ import annotations

from collections import deque

from data.candles import Candle


class CandleCache:
    """Keep the latest N candles for each symbol/timeframe pair."""

    def __init__(self, maxlen: int = 2000) -> None:
        self.maxlen = maxlen
        self._items: dict[tuple[str, str], deque[Candle]] = {}

    def replace(self, symbol: str, timeframe: str, candles: list[Candle]) -> None:
        """Replace a symbol/timeframe cache with sorted candles."""

        key = (symbol, timeframe)
        ordered = sorted(candles, key=lambda candle: candle.open_time)
        self._items[key] = deque(ordered[-self.maxlen :], maxlen=self.maxlen)

    def update(self, candle: Candle) -> None:
        """Append or replace a candle by open_time."""

        key = (candle.symbol, candle.timeframe)
        items = self._items.setdefault(key, deque(maxlen=self.maxlen))
        if items and items[-1].open_time == candle.open_time:
            items[-1] = candle
            return
        if items and items[-1].open_time > candle.open_time:
            self._replace_out_of_order(items, candle)
            return
        items.append(candle)

    def get(self, symbol: str, timeframe: str) -> list[Candle]:
        """Return a copy of cached candles."""

        return list(self._items.get((symbol, timeframe), ()))

    @staticmethod
    def _replace_out_of_order(items: deque[Candle], candle: Candle) -> None:
        existing = list(items)
        for index, item in enumerate(existing):
            if item.open_time == candle.open_time:
                existing[index] = candle
                break
        else:
            existing.append(candle)
        existing.sort(key=lambda item: item.open_time)
        items.clear()
        items.extend(existing)
