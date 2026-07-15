"""Score-only factor library."""

from factors.context_factors import (
    DowntrendStructureScore,
    EMA99ContextScore,
    HammerScore,
    InvertedHammerScore,
    PriorHighBreakoutScore,
    PriorLowBreakdownScore,
    UptrendStructureScore,
)
from factors.pattern_context import (
    DEFAULT_PATTERN_FACTOR_PROFILES,
    FactorSpec,
    PatternContextEvaluation,
    PatternContextScorer,
    PatternFactorProfile,
)
from factors.pattern_factors import (
    AscendingTriangleScore,
    HorizontalResistanceScore,
    HeadAndShouldersTopScore,
    InverseHeadShouldersScore,
    ThreePointTrendlineResistanceScore,
    ThreePointTrendlineSupportScore,
    TriangleScore,
    TrendlineSupportScore,
)

__all__ = [
    "DEFAULT_PATTERN_FACTOR_PROFILES",
    "AscendingTriangleScore",
    "DowntrendStructureScore",
    "EMA99ContextScore",
    "FactorSpec",
    "HammerScore",
    "HorizontalResistanceScore",
    "HeadAndShouldersTopScore",
    "InvertedHammerScore",
    "InverseHeadShouldersScore",
    "PatternContextEvaluation",
    "PatternContextScorer",
    "PatternFactorProfile",
    "PriorHighBreakoutScore",
    "PriorLowBreakdownScore",
    "ThreePointTrendlineResistanceScore",
    "ThreePointTrendlineSupportScore",
    "TriangleScore",
    "TrendlineSupportScore",
    "UptrendStructureScore",
]
