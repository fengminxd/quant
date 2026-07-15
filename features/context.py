"""Shared post-pattern market-context features without future data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.models import Bar, FeatureResult
from indicators.atr import average_true_range
from indicators.ema import exponential_moving_average
from indicators.swing import Pivot, SwingDetector


class ContextFeatureExtractor:
    """Extract trend, EMA, prior-level, and latest-candle geometry."""

    def __init__(
        self,
        swing_detector: SwingDetector | None = None,
        ema_period: int = 99,
        trend_lookback: int = 20,
    ) -> None:
        if ema_period <= 0 or trend_lookback <= 0:
            raise ValueError("periods must be positive")
        self.swing_detector = swing_detector or SwingDetector(min_bars=1)
        self.ema_period = ema_period
        self.trend_lookback = trend_lookback

    def extract(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Return features observable at the final supplied bar close."""

        if not data:
            raise ValueError("at least one bar is required")
        atr = max(average_true_range(data)[-1], 1e-12)
        swings = self._confirmed_swings(data)
        highs = [point for point in swings if point.kind == "high"][-5:]
        lows = [point for point in swings if point.kind == "low"][-5:]
        features: dict[str, FeatureResult] = {}
        features.update(self._trend_features(data, highs, lows))
        features.update(self._ema_features(data, atr))
        features.update(self._level_features(data, highs, lows, atr))
        features.update(self._candle_features(data[-1], atr))
        return features

    def _confirmed_swings(self, data: Sequence[Bar]) -> list[Pivot]:
        detector = self.swing_detector.pivot_detector
        minimum = detector.left + detector.right + 1
        return self.swing_detector.detect(data) if len(data) >= minimum else []

    def _trend_features(
        self,
        data: Sequence[Bar],
        highs: Sequence[Pivot],
        lows: Sequence[Pivot],
    ) -> Mapping[str, FeatureResult]:
        high_count = max(0, len(highs) - 1)
        low_count = max(0, len(lows) - 1)
        higher_highs = sum(right.price > left.price for left, right in zip(highs, highs[1:]))
        lower_highs = sum(right.price < left.price for left, right in zip(highs, highs[1:]))
        higher_lows = sum(right.price > left.price for left, right in zip(lows, lows[1:]))
        lower_lows = sum(right.price < left.price for left, right in zip(lows, lows[1:]))
        start = max(0, len(data) - self.trend_lookback - 1)
        closes = [bar.close for bar in data[start:]]
        travel = sum(abs(right - left) for left, right in zip(closes, closes[1:]))
        efficiency = (closes[-1] - closes[0]) / travel if travel > 0 else 0.0
        comparison_count = high_count + low_count
        sequence_confidence = min(1.0, comparison_count / 4.0)
        return {
            "higher_high_ratio": _feature(
                "higher_high_ratio", higher_highs / high_count if high_count else 0.5,
                min(1.0, high_count / 2.0),
            ),
            "lower_high_ratio": _feature(
                "lower_high_ratio", lower_highs / high_count if high_count else 0.5,
                min(1.0, high_count / 2.0),
            ),
            "higher_low_ratio": _feature(
                "higher_low_ratio", higher_lows / low_count if low_count else 0.5,
                min(1.0, low_count / 2.0),
            ),
            "lower_low_ratio": _feature(
                "lower_low_ratio", lower_lows / low_count if low_count else 0.5,
                min(1.0, low_count / 2.0),
            ),
            "trend_efficiency_signed": _feature(
                "trend_efficiency_signed", efficiency, 1.0 if len(closes) > 1 else 0.0
            ),
            "trend_comparison_count": _feature(
                "trend_comparison_count", float(comparison_count), sequence_confidence
            ),
        }

    def _ema_features(
        self, data: Sequence[Bar], atr: float
    ) -> Mapping[str, FeatureResult]:
        values = exponential_moving_average(data, self.ema_period)
        lookback = min(self.trend_lookback, len(values) - 1)
        slope = (values[-1] - values[-1 - lookback]) / atr if lookback else 0.0
        window = data[-min(self.trend_lookback, len(data)) :]
        ema_window = values[-len(window) :]
        above_ratio = sum(
            bar.close >= ema for bar, ema in zip(window, ema_window)
        ) / len(window)
        confidence = min(1.0, len(data) / self.ema_period)
        return {
            "ema99_value": _feature("ema99_value", values[-1], confidence),
            "ema99_distance_atr": _feature(
                "ema99_distance_atr", (data[-1].close - values[-1]) / atr, confidence
            ),
            "ema99_slope_atr": _feature("ema99_slope_atr", slope, confidence),
            "ema99_above_close_ratio": _feature(
                "ema99_above_close_ratio", above_ratio, confidence
            ),
        }

    @staticmethod
    def _level_features(
        data: Sequence[Bar],
        highs: Sequence[Pivot],
        lows: Sequence[Pivot],
        atr: float,
    ) -> Mapping[str, FeatureResult]:
        latest_index = len(data) - 1
        prior_high = next((point for point in reversed(highs) if point.index < latest_index), None)
        prior_low = next((point for point in reversed(lows) if point.index < latest_index), None)
        bar = data[-1]
        high_confidence = 1.0 if prior_high is not None else 0.0
        low_confidence = 1.0 if prior_low is not None else 0.0
        high_level = prior_high.price if prior_high is not None else bar.high
        low_level = prior_low.price if prior_low is not None else bar.low
        return {
            "prior_swing_high": _feature("prior_swing_high", high_level, high_confidence),
            "prior_swing_low": _feature("prior_swing_low", low_level, low_confidence),
            "breakout_close_distance_atr": _feature(
                "breakout_close_distance_atr", (bar.close - high_level) / atr,
                high_confidence,
            ),
            "breakout_high_distance_atr": _feature(
                "breakout_high_distance_atr", (bar.high - high_level) / atr,
                high_confidence,
            ),
            "breakdown_close_distance_atr": _feature(
                "breakdown_close_distance_atr", (low_level - bar.close) / atr,
                low_confidence,
            ),
            "breakdown_low_distance_atr": _feature(
                "breakdown_low_distance_atr", (low_level - bar.low) / atr,
                low_confidence,
            ),
        }

    @staticmethod
    def _candle_features(bar: Bar, atr: float) -> Mapping[str, FeatureResult]:
        candle_range = bar.high - bar.low
        confidence = 1.0 if candle_range > 0 else 0.0
        denominator = max(candle_range, 1e-12)
        body = abs(bar.close - bar.open)
        body_denominator = max(body, 1e-12)
        body_low = min(bar.open, bar.close)
        body_high = max(bar.open, bar.close)
        return {
            "body_ratio": _feature("body_ratio", body / denominator, confidence),
            "lower_shadow_ratio": _feature(
                "lower_shadow_ratio", (body_low - bar.low) / denominator, confidence
            ),
            "upper_shadow_ratio": _feature(
                "upper_shadow_ratio", (bar.high - body_high) / denominator, confidence
            ),
            "lower_shadow_body_ratio": _feature(
                "lower_shadow_body_ratio", (body_low - bar.low) / body_denominator,
                confidence,
            ),
            "upper_shadow_body_ratio": _feature(
                "upper_shadow_body_ratio", (bar.high - body_high) / body_denominator,
                confidence,
            ),
            "body_bottom_location": _feature(
                "body_bottom_location", (body_low - bar.low) / denominator, confidence
            ),
            "body_top_location": _feature(
                "body_top_location", (body_high - bar.low) / denominator, confidence
            ),
            "close_location": _feature(
                "close_location", (bar.close - bar.low) / denominator, confidence
            ),
            "bullish_body_ratio": _feature(
                "bullish_body_ratio", max(0.0, bar.close - bar.open) / denominator,
                confidence,
            ),
            "bearish_body_ratio": _feature(
                "bearish_body_ratio", max(0.0, bar.open - bar.close) / denominator,
                confidence,
            ),
            "range_atr_ratio": _feature(
                "range_atr_ratio", candle_range / atr, confidence
            ),
        }


def _feature(name: str, value: float, confidence: float) -> FeatureResult:
    return FeatureResult(name, float(value), float(confidence))
