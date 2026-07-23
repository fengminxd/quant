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
from factors.support_confluence import (
    BullishSupportConfluenceScore,
    SupportConfluenceEvaluation,
    SupportConfluenceScorer,
)
from factors.support_lineage import SupportLineageScore
from factors.triangle_context import TriangleBearishContinuationScore
from factors.trade_feasibility import (
    DEFAULT_MINIMUM_NET_REWARD_RISK,
    NetRewardRiskScore,
    PatternTradeFeasibilityEvaluation,
    PatternTradeFeasibilityScorer,
)

__all__ = [
    "DEFAULT_PATTERN_FACTOR_PROFILES",
    "AscendingTriangleScore",
    "BullishSupportConfluenceScore",
    "DowntrendStructureScore",
    "DEFAULT_MINIMUM_NET_REWARD_RISK",
    "EMA99ContextScore",
    "FactorSpec",
    "HammerScore",
    "HorizontalResistanceScore",
    "HeadAndShouldersTopScore",
    "InvertedHammerScore",
    "InverseHeadShouldersScore",
    "NetRewardRiskScore",
    "PatternContextEvaluation",
    "PatternContextScorer",
    "PatternFactorProfile",
    "PatternTradeFeasibilityEvaluation",
    "PatternTradeFeasibilityScorer",
    "PriorityCombinationScorer",
    "PriorityFixedCombinationScore",
    "PriorHighBreakoutScore",
    "PriorLowBreakdownScore",
    "SupportConfluenceEvaluation",
    "SupportConfluenceScorer",
    "SupportLineageScore",
    "TriangleBearishContinuationScore",
    "ThreePointTrendlineResistanceScore",
    "ThreePointTrendlineSupportScore",
    "TriangleScore",
    "TrendlineSupportScore",
    "UptrendStructureScore",
]


def __getattr__(name: str) -> object:
    """Load priority factors lazily to avoid a features/patterns import cycle."""

    if name in {"PriorityCombinationScorer", "PriorityFixedCombinationScore"}:
        from factors.priority_combinations import (
            PriorityCombinationScorer,
            PriorityFixedCombinationScore,
        )

        return {
            "PriorityCombinationScorer": PriorityCombinationScorer,
            "PriorityFixedCombinationScore": PriorityFixedCombinationScore,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
