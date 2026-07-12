"""Pivot, zigzag, and swing detection shared by all patterns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from core.models import Bar
from data.validation import validate_bars

PivotKind = Literal["high", "low"]


@dataclass(frozen=True)
class Pivot:
    """Confirmed local high or low.

    ``index`` is the pivot candle. ``confirmed_at`` is the candle where the
    right window has elapsed, so downstream code can avoid look-ahead bias.
    """

    index: int
    confirmed_at: int
    price: float
    kind: PivotKind


class PivotDetector:
    """Find confirmed local high and low pivots."""

    def __init__(self, left: int = 2, right: int = 2) -> None:
        if left <= 0 or right <= 0:
            raise ValueError("left and right must be positive")
        self.left = left
        self.right = right

    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        """Detect pivots whose confirmation bar exists in ``data``."""

        validate_bars(data, self.left + self.right + 1)
        pivots: list[Pivot] = []
        end = len(data) - self.right
        for index in range(self.left, end):
            window = data[index - self.left : index + self.right + 1]
            high = data[index].high
            low = data[index].low
            is_high = high == max(bar.high for bar in window)
            is_low = low == min(bar.low for bar in window)
            if is_high and not self._has_equal_neighbor_high(window, high, self.left):
                pivots.append(Pivot(index, index + self.right, high, "high"))
            if is_low and not self._has_equal_neighbor_low(window, low, self.left):
                pivots.append(Pivot(index, index + self.right, low, "low"))
        return sorted(pivots, key=lambda pivot: (pivot.confirmed_at, pivot.index, pivot.kind))

    @staticmethod
    def _has_equal_neighbor_high(window: Sequence[Bar], high: float, center: int) -> bool:
        return any(i != center and bar.high == high for i, bar in enumerate(window))

    @staticmethod
    def _has_equal_neighbor_low(window: Sequence[Bar], low: float, center: int) -> bool:
        return any(i != center and bar.low == low for i, bar in enumerate(window))


class ZigZagDetector:
    """Convert pivots into alternating directional turns."""

    def __init__(self, min_percent: float = 0.0) -> None:
        if min_percent < 0:
            raise ValueError("min_percent must be non-negative")
        self.min_percent = min_percent

    def detect(self, pivots: Sequence[Pivot]) -> list[Pivot]:
        """Return alternating pivots after applying a minimum price move."""

        ordered = sorted(pivots, key=lambda pivot: (pivot.confirmed_at, pivot.index))
        turns: list[Pivot] = []
        for pivot in ordered:
            if not turns:
                turns.append(pivot)
                continue
            last = turns[-1]
            if pivot.kind == last.kind:
                turns[-1] = self._more_extreme(last, pivot)
                continue
            if self._move_is_large_enough(last.price, pivot.price):
                turns.append(pivot)
        return turns

    def _move_is_large_enough(self, old_price: float, new_price: float) -> bool:
        if old_price == 0:
            return True
        return abs(new_price - old_price) / abs(old_price) >= self.min_percent

    @staticmethod
    def _more_extreme(left: Pivot, right: Pivot) -> Pivot:
        if left.kind == "high":
            return right if right.price > left.price else left
        return right if right.price < left.price else left


class SwingDetector:
    """Confirm effective swings by denoising and merging pivots."""

    def __init__(
        self,
        pivot_detector: PivotDetector | None = None,
        min_percent: float = 0.0,
        min_bars: int = 1,
    ) -> None:
        if min_bars <= 0:
            raise ValueError("min_bars must be positive")
        self.pivot_detector = pivot_detector or PivotDetector()
        self.zigzag_detector = ZigZagDetector(min_percent=min_percent)
        self.min_bars = min_bars

    def detect(self, data: Sequence[Bar]) -> list[Pivot]:
        """Detect alternating swings with minimum bar spacing."""

        pivots = self.pivot_detector.detect(data)
        turns = self.zigzag_detector.detect(pivots)
        swings: list[Pivot] = []
        for pivot in turns:
            if not swings:
                swings.append(pivot)
                continue
            last = swings[-1]
            if pivot.kind == last.kind:
                swings[-1] = ZigZagDetector._more_extreme(last, pivot)
            elif pivot.index - last.index >= self.min_bars:
                swings.append(pivot)
        return swings

    def lows(self, data: Sequence[Bar]) -> list[Pivot]:
        """Return confirmed swing lows."""

        return [pivot for pivot in self.detect(data) if pivot.kind == "low"]

    def highs(self, data: Sequence[Bar]) -> list[Pivot]:
        """Return confirmed swing highs."""

        return [pivot for pivot in self.detect(data) if pivot.kind == "high"]
