"""Causal entry resolution for the standard anchor-trade report."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.models import Bar, PatternResult
from core.pattern_policy import is_trade_event_enabled
from factors.entry_quality import EntryQualityScore
from features.context import ContextFeatureExtractor, directional_structure_score
from features.entry_retest import EntryRetestFeatureExtractor
from features.trade_plan import TradeDirection
from indicators.atr import average_true_range
from research.pattern_events import PatternAnchor, PatternScanEvent


@dataclass(frozen=True)
class CausalAnchorEntry:
    """First eligible retest/reclaim after one Pattern is observable."""

    direction: TradeDirection
    structure_anchor: PatternAnchor
    entry_anchor: PatternAnchor
    rule: str
    trend_score: float | None
    entry_quality_score: float


class CausalAnchorEntryResolver:
    """Map report events to the first causal structure-zone reclaim."""

    def __init__(
        self,
        entry_extractor: EntryRetestFeatureExtractor | None = None,
        entry_factor: EntryQualityScore | None = None,
    ) -> None:
        self.entry_extractor = entry_extractor or EntryRetestFeatureExtractor()
        self.entry_factor = entry_factor or EntryQualityScore()

    def resolve(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
        detected_index: int,
    ) -> CausalAnchorEntry | None:
        """Return the first eligible close from detection through expiry."""

        if not is_trade_event_enabled(
            event.pattern_id,
            event.priority_combination_id,
        ):
            return None
        definition = self._entry_definition(event, bars)
        if definition is None:
            return None
        direction, structure_anchor, rule, trend_score = definition
        pattern = _pattern_result(event, detected_index)
        final_index = min(
            len(bars) - 1,
            detected_index + self.entry_extractor.max_wait_bars,
        )
        for index in range(detected_index + 1, final_index + 1):
            window = bars[: index + 1]
            atr = max(average_true_range(window)[-1], 1e-12)
            assessment = self.entry_extractor.extract(
                pattern, window, index, atr
            )
            if not assessment.eligible or assessment.direction != direction:
                continue
            quality = self.entry_factor.calculate(assessment.features)
            entry = PatternAnchor(index, bars[index].timestamp, bars[index].close)
            return CausalAnchorEntry(
                direction,
                structure_anchor,
                entry,
                f"{rule} zone retest and close reclaim",
                trend_score,
                quality.score,
            )
        return None

    def _entry_definition(
        self,
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> tuple[
        TradeDirection,
        PatternAnchor,
        str,
        float | None,
    ] | None:
        group = event.anchor_groups[0] if event.anchor_groups else event.anchors
        definitions: dict[str, tuple[TradeDirection, int, str]] = {
            "PATTERN_003": ("bullish", 2, "third trendline-support anchor"),
            "PATTERN_004": ("bullish", 1, "second horizontal-support anchor"),
            "PATTERN_005": ("bearish", 2, "third trendline-resistance anchor"),
            "PATTERN_006": ("bearish", 1, "second horizontal-resistance anchor"),
            "PATTERN_007": ("bullish", 2, "right-shoulder"),
            "PATTERN_008": ("bearish", 2, "right-shoulder"),
        }
        defined = definitions.get(event.pattern_id)
        if defined is not None:
            direction, position, rule = defined
            ordered = sorted(group, key=lambda anchor: anchor.index)
            if len(ordered) <= position:
                return None
            return direction, ordered[position], rule, None
        if event.pattern_id == "PATTERN_002":
            return self._triangle_entry(event, bars)
        return None

    @staticmethod
    def _triangle_entry(
        event: PatternScanEvent,
        bars: Sequence[Bar],
    ) -> tuple[
        TradeDirection,
        PatternAnchor,
        str,
        float,
    ] | None:
        if len(event.anchor_groups) < 2:
            return None
        upper = sorted(event.anchor_groups[0], key=lambda anchor: anchor.index)
        lower = sorted(event.anchor_groups[1], key=lambda anchor: anchor.index)
        first_anchor = min(anchor.index for anchor in (*upper, *lower))
        features = ContextFeatureExtractor().extract(bars[: first_anchor + 1])
        up_score, _, uptrend = directional_structure_score(features, bullish=True)
        down_score, _, downtrend = directional_structure_score(
            features, bullish=False
        )
        candidates: list[
            tuple[float, TradeDirection, PatternAnchor, str]
        ] = []
        if uptrend and len(lower) >= 3:
            candidates.append(
                (up_score, "bullish", lower[2], "uptrend lower-boundary P3")
            )
        if downtrend and len(upper) >= 3:
            candidates.append(
                (down_score, "bearish", upper[2], "downtrend upper-boundary P3")
            )
        if not candidates:
            return None
        score, direction, anchor, rule = max(candidates, key=lambda item: item[0])
        return direction, anchor, rule, score


def _pattern_result(
    event: PatternScanEvent,
    detected_index: int,
) -> PatternResult:
    groups = event.anchor_groups or (event.anchors,)
    ordered = tuple(sorted(groups[0], key=lambda anchor: anchor.index))
    geometry: dict[str, object]
    if event.pattern_id == "PATTERN_002" and len(groups) >= 2:
        upper = sorted(groups[0], key=lambda anchor: anchor.index)
        lower = sorted(groups[1], key=lambda anchor: anchor.index)
        geometry = {
            "upper_points": _pairs(upper),
            "lower_points": _pairs(lower),
        }
    elif event.pattern_id in {"PATTERN_004", "PATTERN_006"}:
        position = 1
        geometry = {"level": ordered[position].price} if len(ordered) > position else {}
    else:
        geometry = {"points": _pairs(ordered)}
    return PatternResult(
        event.pattern_id,
        event.pattern_name,
        True,
        event.score,
        geometry=geometry,
        metadata={"detected_at_index": detected_index, "state": "structure_confirmed"},
    )


def _pairs(anchors: Sequence[PatternAnchor]) -> list[tuple[int, float]]:
    return [(anchor.index, anchor.price) for anchor in anchors]
