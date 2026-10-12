"""Symbol-specific timeframe eligibility for research notifications."""

from notifications.config import NOTIFICATION_TIMEFRAMES


TRADEFI_SYMBOLS = frozenset({
    "XAU", "XAG", "CL", "SPCX", "MU", "SNDK", "SKHYNIX", "NVDA",
    "DRAM", "SOXL", "KORU", "MSTR",
})


def notification_timeframe_enabled(symbol: str, timeframe: str) -> bool:
    """Allow 15m for crypto symbols and 1h/4h for all symbols."""

    base = symbol.upper().removesuffix("USDT")
    return timeframe in NOTIFICATION_TIMEFRAMES and (
        timeframe != "15m" or base not in TRADEFI_SYMBOLS
    )
