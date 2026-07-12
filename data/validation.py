"""OHLCV validation utilities."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Bar


def validate_bars(data: Sequence[Bar], min_length: int = 1) -> None:
    """Validate that a bar sequence is usable by deterministic detectors."""

    if len(data) < min_length:
        raise ValueError(f"at least {min_length} bars are required")
