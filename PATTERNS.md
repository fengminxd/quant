# PATTERNS.md

# Price Action Pattern Library

## Purpose

Define chart patterns in a machine-readable specification.

## Standard Template

``` yaml
id:
name:
category:
market_logic:
geometry:
detection_rules:
required_features:
factor_mapping:
entry_rules:
exit_rules:
invalidation:
python_module:
```

------------------------------------------------------------------------

# PATTERN_001 Trendline Support

## Market Logic

Price repeatedly finds support on an ascending trendline.

## Geometry

-   At least 3 swing lows
-   P1 \< P2 \< P3
-   P1-P2 \>= 5 bars
-   P2-P3 \>= 5 bars

## Detection Rules

-   Evaluate all swing-low combinations.
-   Fit error \< 0.5 ATR.
-   Prefer longest span.
-   Prefer highest touch count.
-   Penalize broken trendlines.

## Required Features

-   touch_count
-   line_span
-   line_angle
-   fit_error
-   atr_distance
-   break_count
-   trend_strength
-   volume_ratio

## Factor Mapping

TrendlineSupportScore

## Entry

Price retests trendline with bullish confirmation.

## Exit

Two confirmed closes below trendline.

## Python Module

patterns/trendline_support.py

------------------------------------------------------------------------

# PATTERN_002 Ascending Triangle

## Market Logic

Buyers raise lows while sellers defend one resistance.

## Geometry

-   Flat resistance
-   Rising swing lows

## Detection Rules

-   High deviation \< 0.3 ATR

-   =3 higher lows

-   ATR compression

-   Volume contraction

-   Breakout volume \> MA20

## Required Features

-   resistance_flatness
-   higher_low_score
-   atr_compression
-   volume_contraction
-   breakout_strength
-   breakout_volume

## Factor Mapping

AscendingTriangleScore

## Entry

Close above resistance with volume confirmation.

## Exit

Close back below resistance.

## Python Module

patterns/ascending_triangle.py
