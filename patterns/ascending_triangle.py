"""Backward-compatible import for PATTERN_002 Triangle."""

from patterns.triangle import Triangle

AscendingTriangle = Triangle

__all__ = ["AscendingTriangle", "Triangle"]
