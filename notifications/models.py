"""Immutable notification matches and geometry helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from core.models import FactorResult, PatternResult


@dataclass(frozen=True)
class NotificationAnchor:
    """One chart annotation extracted from Pattern geometry."""

    label: str
    index: int
    price: float


@dataclass(frozen=True)
class NotificationMatch:
    """One right-edge Pattern observation for Telegram delivery."""

    symbol: str
    timeframe: str
    detected_timestamp: int | str
    pattern: PatternResult
    combination: FactorResult | None = None

    @property
    def rule(self) -> str:
        metadata = self.pattern.metadata
        if self.pattern.pattern_id == "PATTERN_002":
            return str(metadata.get("triangle_type", metadata.get("rule", self.pattern.name)))
        return str(metadata.get("rule_type", metadata.get("rule", self.pattern.name)))

    @property
    def combination_id(self) -> str | None:
        if self.combination is None or not self.combination.metadata.get("active"):
            return None
        value = self.combination.metadata.get("combination_id")
        return str(value) if value else None

    @property
    def matched_conditions(self) -> tuple[str, ...]:
        if self.combination is None:
            return ()
        return tuple(
            str(value)
            for value in self.combination.metadata.get("matched_conditions", ())
        )

    @property
    def anchors(self) -> tuple[NotificationAnchor, ...]:
        return tuple(_geometry_anchors(self.pattern))

    @property
    def identity(self) -> str:
        payload = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "pattern": self.pattern.pattern_id,
            "rule": self.rule,
            "detected": self.detected_timestamp,
            "anchors": [
                (anchor.label, anchor.index, anchor.price) for anchor in self.anchors
            ],
            "combination": self.combination_id,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _geometry_anchors(result: PatternResult) -> Iterable[NotificationAnchor]:
    geometry = result.geometry
    if result.pattern_id == "PATTERN_002":
        yield from _labeled_points(geometry.get("upper_points", ()), "U")
        yield from _labeled_points(geometry.get("lower_points", ()), "L")
        return
    labels = ("LS", "H", "RS") if result.pattern_id in {"PATTERN_007", "PATTERN_008"} else ()
    yield from _labeled_points(geometry.get("points", ()), "P", labels)
    if result.pattern_id in {"PATTERN_007", "PATTERN_008"}:
        yield from _labeled_points(geometry.get("neckline_points", ()), "N")


def _labeled_points(
    raw: object,
    prefix: str,
    labels: Sequence[str] = (),
) -> Iterable[NotificationAnchor]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return
    number = 0
    for point in raw:
        if (
            not isinstance(point, Sequence)
            or isinstance(point, (str, bytes))
            or len(point) < 2
            or not isinstance(point[0], (int, float))
            or not isinstance(point[1], (int, float))
        ):
            continue
        label = labels[number] if number < len(labels) else f"{prefix}{number + 1}"
        number += 1
        yield NotificationAnchor(label, int(point[0]), float(point[1]))
