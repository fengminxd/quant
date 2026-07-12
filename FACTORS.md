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
