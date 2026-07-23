"""Causal historical-level relationships for priority pattern combinations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.models import Bar
from indicators.atr import average_true_range
from indicators.swing import Pivot, SwingDetector
from patterns.support_levels import (
    all_closes_above_level,
    body_pierce_count,
    breakout_retest_contact,
    double_bottom_contact,
    first_accepted_breakout,
    horizontal_resistance_contacts,
    post_breakout_closes_hold,
)


@dataclass(frozen=True)
class PriorLevelMatch:
    """One earlier confirmed swing linked to an explicit pattern anchor."""

    matched: bool
    rule_type: str
    source_index: int = -1
    target_index: int = -1
    level: float = 0.0
    level_error: float = 0.0
    breakout_index: int = -1
    contact_overlap: float = 0.0


class PriorityLevelContextMatcher:
    """Validate horizontal ancestry without requiring the target to be re-pivoted."""

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        min_span: int = 40,
        breakout_hold_atr_tolerance_ratio: float = 0.1,
        price_epsilon: float = 1e-9,
    ) -> None:
        if min_span <= 0:
            raise ValueError("min_span must be positive")
        if min(
            breakout_hold_atr_tolerance_ratio,
            price_epsilon,
        ) < 0.0:
            raise ValueError("price tolerances must be non-negative")
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.min_span = min_span
        self.breakout_hold_atr_tolerance_ratio = (
            breakout_hold_atr_tolerance_ratio
        )
        self.price_epsilon = price_epsilon

    def double_bottom(
        self, data: Sequence[Bar], target_index: int, as_of_index: int
    ) -> PriorLevelMatch:
        """Match an explicit low anchor with an earlier confirmed swing low."""

        self._validate_indexes(data, target_index, as_of_index)
        candidates: list[PriorLevelMatch] = []
        for source in self._prior_swings(data, target_index, as_of_index, "low"):
            contact = double_bottom_contact(
                data[source.index],
                data[target_index],
                price_epsilon=self.price_epsilon,
            )
            if contact is None:
                continue
            if body_pierce_count(
                data, source.index, target_index, contact.level
            ) != 0:
                continue
            if not all_closes_above_level(
                data, source.index, target_index, contact.level
            ):
                continue
            candidates.append(
                PriorLevelMatch(
                    True,
                    "double_swing_low",
                    source.index,
                    target_index,
                    contact.level,
                    contact.gap,
                    contact_overlap=contact.overlap_width,
                )
            )
        return max(
            candidates,
            key=lambda item: (item.target_index - item.source_index, -item.level_error),
            default=PriorLevelMatch(False, "double_swing_low", target_index=target_index),
        )

    def breakout_retest_support(
        self, data: Sequence[Bar], target_index: int, as_of_index: int
    ) -> PriorLevelMatch:
        """Match an explicit low anchor to a causally accepted prior-high breakout."""

        self._validate_indexes(data, target_index, as_of_index)
        hold_tolerance = self._breakout_hold_tolerance(data, target_index)
        candidates: list[PriorLevelMatch] = []
        for source in self._prior_swings(data, target_index, as_of_index, "high"):
            contact = breakout_retest_contact(
                data[source.index],
                data[target_index],
                price_epsilon=self.price_epsilon,
            )
            if contact is None:
                continue
            breakout = first_accepted_breakout(
                data, source.index + 1, target_index, contact.level
            )
            if breakout is None:
                continue
            if not post_breakout_closes_hold(
                data,
                source.index,
                breakout,
                target_index,
                contact.level,
                hold_tolerance,
            ):
                continue
            candidates.append(
                PriorLevelMatch(
                    True,
                    "breakout_retest",
                    source.index,
                    target_index,
                    contact.level,
                    contact.gap,
                    breakout,
                    contact.overlap_width,
                )
            )
        return max(
            candidates,
            key=lambda item: (item.source_index, -item.level_error),
            default=PriorLevelMatch(False, "breakout_retest", target_index=target_index),
        )

    def horizontal_resistance(
        self, data: Sequence[Bar], target_index: int, as_of_index: int
    ) -> PriorLevelMatch:
        """Match an explicit high anchor to an unpenetrated earlier swing high."""

        self._validate_indexes(data, target_index, as_of_index)
        candidates: list[PriorLevelMatch] = []
        target = data[target_index]
        for source in self._prior_swings(data, target_index, as_of_index, "high"):
            source_bar = data[source.index]
            contacts = horizontal_resistance_contacts(
                source_bar,
                target,
                price_epsilon=self.price_epsilon,
            )
            for contact in contacts:
                middle = data[source.index + 1 : target_index]
                if any(
                    bar.high > contact.level + self.price_epsilon
                    for bar in middle
                ):
                    continue
                if any(
                    bar.open > contact.level + self.price_epsilon
                    for bar in middle
                ):
                    continue
                overshoot = max(0.0, source.price - contact.level)
                candidates.append(
                    PriorLevelMatch(
                        True,
                        "strict_two_swing_horizontal_resistance",
                        source.index,
                        target_index,
                        contact.level,
                        overshoot,
                        contact_overlap=contact.overlap_width,
                    )
                )
        return max(
            candidates,
            key=lambda item: (item.target_index - item.source_index, -item.level_error),
            default=PriorLevelMatch(
                False,
                "strict_two_swing_horizontal_resistance",
                target_index=target_index,
            ),
        )

    def _prior_swings(
        self,
        data: Sequence[Bar],
        target_index: int,
        as_of_index: int,
        kind: str,
    ) -> list[Pivot]:
        visible = data[: as_of_index + 1]
        detector = self.swing_detector.pivot_detector
        minimum = detector.left + detector.right + 1
        if len(visible) < minimum:
            return []
        return [
            pivot
            for pivot in self.swing_detector.detect(visible)
            if pivot.kind == kind
            and pivot.index < target_index
            and target_index - pivot.index >= self.min_span
        ]

    def _breakout_hold_tolerance(
        self, data: Sequence[Bar], target_index: int
    ) -> float:
        atr = self._atr(data, target_index)
        return max(
            self.price_epsilon,
            atr * self.breakout_hold_atr_tolerance_ratio,
        )

    @staticmethod
    def _atr(data: Sequence[Bar], target_index: int) -> float:
        return average_true_range(data[: target_index + 1])[-1]

    @staticmethod
    def _validate_indexes(
        data: Sequence[Bar], target_index: int, as_of_index: int
    ) -> None:
        if not data:
            raise ValueError("at least one bar is required")
        if not 0 <= target_index <= as_of_index < len(data):
            raise ValueError("level-context indexes are outside supplied data")
