# FACTORS.md

# Factor Library

## Purpose

Convert reusable features into scoring factors.

------------------------------------------------------------------------

# FACTOR_001 TrendlineSupportScore

## Market Logic

Reliable trendlines have higher continuation probability.

## Inputs

-   touch_count
-   line_span
-   trend_strength
-   volume_ratio
-   fit_error

## Formula

``` text
0.30*touch_count
+0.25*line_span
+0.20*trend_strength
+0.15*volume_ratio
-0.10*fit_error
```

## Output

0\~100

## Validation

-   IC
-   RankIC
-   Sharpe
-   Max Drawdown

------------------------------------------------------------------------

# FACTOR_002 AscendingTriangleScore

## Inputs

-   resistance_flatness
-   higher_low_score
-   atr_compression
-   volume_contraction
-   breakout_strength

## Formula

``` text
0.25*resistance_flatness
+0.25*higher_low_score
+0.20*atr_compression
+0.15*volume_contraction
+0.15*breakout_strength
```

## Output

0\~100

## Validation

-   Walk-forward
-   Out-of-sample
-   Transaction cost
-   Profit factor

------------------------------------------------------------------------

## General Rules

-   Factors never emit Buy/Sell.
-   Factors output scores only.
-   Strategies combine multiple factors.

------------------------------------------------------------------------

# FACTOR_003 ThreePointTrendlineResistanceScore

## Market Logic

Long, accurately fitted descending boundaries with no body acceptance and
repeated upper-shadow rejection provide stronger structural resistance evidence.

## Inputs

-   line_span
-   fit_error_atr
-   line_slope
-   body_violation_count
-   upper_shadow_cross_count

## Formula

``` text
0.25*span_quality
+0.25*fit_quality
+0.20*negative_slope
+0.20*body_integrity
+0.10*upper_shadow_interaction
```

## Output

0\~100 structural score; never Buy/Sell.

## Validation

-   Walk-forward and rolling out-of-sample tests
-   IC and RankIC against forward returns
-   Fee, slippage, and funding sensitivity
-   Monte Carlo trade-order resampling

------------------------------------------------------------------------

# FACTOR_004 HorizontalResistanceScore

## Market Logic

Longer-lived, closely aligned resistance with clean price clearance and low
intervening opens is stronger evidence of persistent seller defense.

## Inputs

-   span
-   anchor_overshoot_atr
-   penetration_count
-   open_violation_count
-   intermediate_clearance_atr
-   intermediate_open_margin_atr

## Formula

``` text
0.30*span_quality
+0.30*anchor_alignment
+0.25*intermediate_clearance
+0.15*intermediate_open_margin
```

## Output

0\~100 structural score; never Buy/Sell.

## Validation

-   Forward-return IC and RankIC by timeframe and market regime
-   Walk-forward and rolling out-of-sample tests
-   Fee, slippage, and funding sensitivity
-   Monte Carlo trade-order and execution-cost resampling

------------------------------------------------------------------------

# FACTOR_005 InverseHeadShouldersScore

## Market Logic

A broad pattern with aligned shoulders, a meaningfully deeper head, balanced
duration, a preceding decline, and an accepted neckline breakout is stronger
evidence of selling exhaustion than a noisy three-low sequence.

## Inputs

-   span
-   shoulder_price_error_atr
-   head_depth_atr
-   head_extreme_error_atr
-   duration_asymmetry
-   prior_decline_atr
-   breakout_confirmed
-   breakout_distance_atr
-   breakout_volume_ratio

## Formula

``` text
0.20*span_quality
+0.25*shoulder_alignment
+0.20*head_zone_quality
+0.15*duration_symmetry
+0.05*prior_decline
+0.15*breakout_quality
```

Breakout quality combines close distance above the projected neckline and
volume relative to the preceding 20 bars. An unconfirmed structure receives
zero breakout-quality contribution.

## Output

0\~100 structural and confirmation score; never Buy/Sell.

## Validation

-   Forward-return IC and RankIC from structure and breakout confirmation separately
-   15m, 1h, and 4h walk-forward and rolling out-of-sample tests
-   Trend, consolidation, and high-volatility regime segmentation
-   Fee, slippage, and funding sensitivity
-   Monte Carlo trade-order and execution-cost resampling

------------------------------------------------------------------------

# FACTOR_006 HeadAndShouldersTopScore

## Market Logic

A broad top with aligned shoulders, a distinct head liquidity zone, balanced
duration, a preceding advance, and an accepted neckline breakdown is stronger
evidence of buying exhaustion than an arbitrary three-high sequence.

## Inputs

-   span
-   shoulder_price_error_atr
-   head_height_atr
-   head_extreme_error_atr
-   duration_asymmetry
-   prior_advance_atr
-   breakdown_confirmed
-   breakdown_distance_atr
-   breakdown_volume_ratio

## Formula

``` text
0.20*span_quality
+0.25*shoulder_alignment
+0.20*head_zone_quality
+0.15*duration_symmetry
+0.05*prior_advance
+0.15*breakdown_quality
```

Head-zone quality combines height above the shoulders and distance from the
absolute zone high. Breakdown quality combines close distance beneath the
projected neckline and volume relative to the preceding 20 bars.

## Output

0\~100 structural and confirmation score; never Buy/Sell.

## Validation

-   Forward-return IC and RankIC from structure and breakdown confirmation separately
-   15m, 1h, and 4h walk-forward and rolling out-of-sample tests
-   Trend, consolidation, and high-volatility regime segmentation
-   Fee, slippage, and funding sensitivity
-   Monte Carlo trade-order and execution-cost resampling
