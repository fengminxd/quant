"""Immutable evidence records emitted by historical pattern scans."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatternAnchor:
    """One absolute candle anchor supporting a detected structure."""

    index: int
    timestamp: int | str
    price: float


@dataclass(frozen=True)
class PriorityLevelRelation:
    """A prior level anchor linked to one fixed-combination target anchor."""

    condition: str
    rule_type: str
    source: PatternAnchor
    target: PatternAnchor
    level: float


@dataclass(frozen=True)
class PatternScanEvent:
    """A de-duplicated historical structure known at one closed candle."""

    symbol: str
    timeframe: str
    pattern_id: str
    pattern_name: str
    rule: str
    score: float
    detected_timestamp: int | str
    anchors: tuple[PatternAnchor, ...]
    anchor_groups: tuple[tuple[PatternAnchor, ...], ...] = ()
    line_groups: tuple[tuple[PatternAnchor, ...], ...] = ()
    priority_fixed_combination: bool = False
    priority_combination_id: str | None = None
    priority_combination_score: float = 0.0
    priority_matched_conditions: tuple[str, ...] = ()
    priority_level_sources: tuple[PatternAnchor, ...] = ()
    priority_level_relations: tuple[PriorityLevelRelation, ...] = ()

    @property
    def first_anchor_index(self) -> int:
        """Return the earliest parent-Pattern anchor index."""

        return min(anchor.index for anchor in self.anchors)

    @property
    def last_anchor_index(self) -> int:
        """Return the latest parent-Pattern anchor index."""

        return max(anchor.index for anchor in self.anchors)

    @property
    def identity(self) -> tuple[str, str, tuple[int | str, ...]]:
        """Return the stable rule-and-anchor identity used for de-duplication."""

        return self.pattern_id, self.rule, tuple(
            anchor.timestamp for anchor in self.anchors
        )

    @property
    def displayed_level_sources(self) -> tuple[PatternAnchor, ...]:
        """Return relation sources, falling back to legacy source-only events."""

        candidates = (
            tuple(relation.source for relation in self.priority_level_relations)
            or self.priority_level_sources
        )
        unique = {(anchor.index, anchor.price): anchor for anchor in candidates}
        return tuple(
            sorted(unique.values(), key=lambda anchor: (anchor.index, anchor.price))
        )
