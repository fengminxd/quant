from __future__ import annotations

from data.binance_futures import SUPPORTED_CONTRACT_TYPES


def test_binance_filter_accepts_crypto_and_tradifi_perpetual_contract_types() -> None:
    assert "PERPETUAL" in SUPPORTED_CONTRACT_TYPES
    assert "TRADIFI_PERPETUAL" in SUPPORTED_CONTRACT_TYPES
