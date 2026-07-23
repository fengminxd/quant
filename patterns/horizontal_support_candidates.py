"""Candidate search for double-bottom and strict breakout-retest support."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from core.models import Bar
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector
from patterns.support_levels import (
    all_closes_above_level,
    body_pierce_count,
    breakout_retest_contact,
    double_bottom_contact,
    first_accepted_breakout,
    post_breakout_closes_hold,
)


@dataclass(frozen=True)
class HorizontalSupportCandidate:
    """Horizontal support candidate from two explicit price-action anchors."""

    rule_type: str
    points: tuple[Pivot, Pivot]
    level: float
    contact_tolerance: float
    hold_tolerance: float
    pierce_count: int
    level_error: float
    breakout_index: int | None = None
    contact_overlap: float = 0.0


class HorizontalSupportCandidateFinder:
    """Find support candidates while keeping contact and hold rules separate."""

    def __init__(
        self,
        swing_detector: SwingDetector,
        min_span: int,
        breakout_hold_atr_tolerance_ratio: float,
        price_epsilon: float,
    ) -> None:
        self.swing_detector = swing_detector
        self.min_span = min_span
        self.breakout_hold_atr_tolerance_ratio = (
            breakout_hold_atr_tolerance_ratio
        )
        self.price_epsilon = price_epsilon

    def best(
        self, data: Sequence[Bar], anchor_index: int | None = None
    ) -> HorizontalSupportCandidate | None:
        """Return the highest-ranked candidate, optionally at one right anchor."""

        swings = self.swing_detector.detect(data)
        atr_values = average_true_range(data)
        candidates = self._double_bottom_candidates(data, swings)
        candidates.extend(self._breakout_retest_candidates(data, swings, atr_values))
        if anchor_index is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.points[1].index == anchor_index
            ]
        return max(candidates, key=self._rank, default=None)

    def _double_bottom_candidates(
        self,
        data: Sequence[Bar],
        swings: Sequence[Pivot],
    ) -> list[HorizontalSupportCandidate]:
        lows = [pivot for pivot in swings if pivot.kind == "low"]
        candidates: list[HorizontalSupportCandidate] = []
        for left, right in combinations(lows, 2):
            if right.index - left.index < self.min_span:
                continue
            contact = double_bottom_contact(
                data[left.index],
                data[right.index],
                price_epsilon=self.price_epsilon,
            )
            if contact is None:
                continue
            if body_pierce_count(
                data, left.index, right.index, contact.level
            ) != 0:
                continue
            if not all_closes_above_level(
                data, left.index, right.index, contact.level
            ):
                continue
            candidates.append(
                HorizontalSupportCandidate(
                    "double_swing_low",
                    (left, right),
                    contact.level,
                    self.price_epsilon,
                    0.0,
                    0,
                    contact.gap,
                    contact_overlap=contact.overlap_width,
                )
            )
        return candidates

    def _breakout_retest_candidates(
        self,
        data: Sequence[Bar],
        swings: Sequence[Pivot],
        atr_values: Sequence[float],
    ) -> list[HorizontalSupportCandidate]:
        highs = [pivot for pivot in swings if pivot.kind == "high"]
        lows = [pivot for pivot in swings if pivot.kind == "low"]
        candidates: list[HorizontalSupportCandidate] = []
        for high in highs:
            for low in lows:
                if low.index <= high.index or low.index - high.index < self.min_span:
                    continue
                contact = breakout_retest_contact(
                    data[high.index],
                    data[low.index],
                    price_epsilon=self.price_epsilon,
                )
                if contact is None:
                    continue
                hold_tolerance = max(
                    self.price_epsilon,
                    atr_values[low.index] * self.breakout_hold_atr_tolerance_ratio,
                )
                breakout = first_accepted_breakout(
                    data, high.index + 1, low.index, contact.level
                )
                if breakout is None:
                    continue
                if not post_breakout_closes_hold(
                    data,
                    high.index,
                    breakout,
                    low.index,
                    contact.level,
                    hold_tolerance,
                ):
                    continue
                candidates.append(
                    HorizontalSupportCandidate(
                        "breakout_retest",
                        (high, low),
                        contact.level,
                        self.price_epsilon,
                        hold_tolerance,
                        1,
                        contact.gap,
                        breakout,
                        contact.overlap_width,
                    )
                )
        return candidates

    @staticmethod
    def _rank(
        candidate: HorizontalSupportCandidate,
    ) -> tuple[float, float, float, float, float, float]:
        left, right = candidate.points
        rule_priority = float(candidate.rule_type == "breakout_retest")
        recency_or_span = (
            float(left.index)
            if candidate.breakout_index is not None
            else float(right.index - left.index)
        )
        retest_recency = (
            float(right.index) if candidate.breakout_index is not None else 0.0
        )
        return (
            rule_priority,
            recency_or_span,
            retest_recency,
            candidate.contact_overlap,
            -candidate.level_error,
            -float(candidate.pierce_count),
        )
