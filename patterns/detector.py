"""Composable pattern detector registry."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from core.base import Pattern
from core.models import Bar, PatternResult


class PatternDetector:
    """Run multiple pattern detectors on the same OHLCV history."""

    def __init__(self, patterns: Iterable[Pattern] | None = None) -> None:
        self.patterns = list(patterns or [])

    def register(self, pattern: Pattern) -> None:
        """Register an additional pattern detector."""

        self.patterns.append(pattern)

    def detect(self, data: Sequence[Bar]) -> list[PatternResult]:
        """Detect all registered patterns."""

        return [pattern.detect(data) for pattern in self.patterns]
