"""Central trading/report enablement policy for Pattern rules."""

from __future__ import annotations


KNOWN_PATTERN_IDS = tuple(f"PATTERN_{number:03d}" for number in range(1, 9))

# Implementations remain available for research and direct detector tests.
DISABLED_TRADING_PATTERN_IDS = frozenset(
    {"PATTERN_001", "PATTERN_005", "PATTERN_008"}
)
COMBINATION_ONLY_PATTERN_IDS = frozenset({"PATTERN_006"})
DISABLED_FIXED_COMBINATION_IDS = frozenset({"FIXED_COMBO_006"})

ACTIVE_TRADING_PATTERN_IDS = tuple(
    pattern_id
    for pattern_id in KNOWN_PATTERN_IDS
    if pattern_id not in DISABLED_TRADING_PATTERN_IDS
    and pattern_id not in COMBINATION_ONLY_PATTERN_IDS
)


def is_trading_pattern_enabled(pattern_id: str) -> bool:
    """Return whether a Pattern may create a standalone trade."""

    return (
        pattern_id in KNOWN_PATTERN_IDS
        and pattern_id not in DISABLED_TRADING_PATTERN_IDS
        and pattern_id not in COMBINATION_ONLY_PATTERN_IDS
    )


def is_pattern_analysis_enabled(pattern_id: str) -> bool:
    """Return whether a Pattern may be evaluated as combination evidence."""

    return (
        pattern_id in KNOWN_PATTERN_IDS
        and pattern_id not in DISABLED_TRADING_PATTERN_IDS
    )


def is_fixed_combination_enabled(combination_id: str | None) -> bool:
    """Return whether a fixed combination may enter a trading cohort."""

    return (
        combination_id is not None
        and combination_id not in DISABLED_FIXED_COMBINATION_IDS
    )


def is_trade_event_enabled(
    pattern_id: str,
    combination_id: str | None,
) -> bool:
    """Apply standalone, combination-only, and disabled-combination policy."""

    if not is_pattern_analysis_enabled(pattern_id):
        return False
    if combination_id in DISABLED_FIXED_COMBINATION_IDS:
        return False
    if pattern_id == "PATTERN_006":
        return combination_id == "FIXED_COMBO_002"
    return is_trading_pattern_enabled(pattern_id)
