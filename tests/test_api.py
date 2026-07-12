from __future__ import annotations

import pytest

from core.models import Bar, FeatureResult, PatternResult


def test_bar_validates_ohlcv() -> None:
    with pytest.raises(ValueError):
        Bar(timestamp=1, open=10, high=9, low=8, close=8.5, volume=1)


def test_feature_and_pattern_results_are_typed() -> None:
    feature = FeatureResult("touch_count", 3.0, 1.0)
    result = PatternResult("P", "Pattern", True, 80.0, {"touch_count": feature})

    assert result.detected is True
    assert result.features["touch_count"].value == 3.0
