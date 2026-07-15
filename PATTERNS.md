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

# PATTERN_002 Triangle

## Market Logic

Swing highs and lows form two inward boundaries as price acceptance narrows.
The upper boundary may be horizontal or descending; the lower boundary may be
horizontal or rising. The structure is direction neutral until price closes
outside either projected boundary.

## Geometry

-   At least 3 confirmed swing highs on the fitted upper boundary
-   At least 3 confirmed swing lows on the fitted lower boundary
-   Upper slope is horizontal or negative
-   Lower slope is horizontal or positive
-   The two fitted boundaries overlap for at least 5 bars
-   Boundary distance contracts by at least 5%
-   Parallel horizontal boxes and diverging boundaries are rejected

## Detection Rules

-   Evaluate all 3-point combinations among the latest 8 confirmed highs/lows.
-   Each boundary spans at least 5 complete bar intervals.
-   Boundary regression RMSE must be no more than 0.5 ATR.
-   A normalized slope within +/-0.02 ATR per bar is treated as horizontal.
-   No confirmed swing may violate a fitted boundary beyond the fit tolerance.
-   Prefer the longest overlapping boundary span, then stronger convergence and fit.
-   Score upside breakouts and downside breakdowns symmetrically.

## Required Features

-   upper_slope_atr_per_bar
-   lower_slope_atr_per_bar
-   upper_fit_error_atr
-   lower_fit_error_atr
-   boundary_direction_score
-   boundary_fit_score
-   convergence_ratio
-   convergence_score
-   overlap_span
-   atr_compression
-   volume_contraction
-   breakout_strength
-   upside_breakout_strength
-   downside_breakdown_strength
-   breakout_volume

## Factor Mapping

TriangleScore

## States

-   structure_confirmed
-   upside_breakout_confirmed
-   downside_breakout_confirmed

## Reference Case

SUI 4h from 2026-06-29 04:00 to 2026-07-14 08:00 UTC+8 is a
symmetrical triangle under this rule. Its upper and lower normalized slopes are
-0.04538 and +0.04326 ATR per bar, and its structural score is 58.7907.

## Python Module

patterns/triangle.py

------------------------------------------------------------------------

# PATTERN_003 Three Point Trendline Support

## Market Logic

Three rising swing lows show buyers defending progressively higher prices.
Lower shadows represent liquidity tests below the locally accepted price; a
body crossing the projected line instead indicates acceptance through support
and invalidates the structure.

## Geometry

-   Exactly 3 selected confirmed swing-low anchors
-   P1 \< P2 \< P3 (positive slope)
-   P1-P3 \>= 40 complete bars
-   P1-P2 \>= 10 complete bars
-   P2-P3 \>= 10 complete bars

## Detection Rules

-   Evaluate all confirmed swing-low combinations; they need not be consecutive.
-   Keep swing denoising independent from the trendline anchor-spacing rules.
-   The middle swing low must fit the P1-P3 line within the configured ATR tolerance.
-   Each anchor line contact must be in or sufficiently close to the lower shadow.
-   No non-anchor candle body may cross the line between P1 and P3.
-   Emit only after the third swing low's right-side confirmation window exists.
-   Candle timestamps are opening timestamps; rules are timeframe agnostic.
-   Prefer the longest span, then the smallest fit error.

## Required Features

-   touch_count
-   line_span
-   leg_1_span
-   leg_2_span
-   line_slope
-   line_angle
-   fit_error
-   fit_error_atr
-   body_violation_count
-   tolerance

## Factor Mapping

ThreePointTrendlineSupportScore

## Reference Case

HYPE 15m, UTC+8 opening timestamps: 2026-07-14 11:15,
2026-07-14 20:00, and 2026-07-15 09:45. The corresponding Binance lows are
62.555, 63.588, and 64.863, covering 35 and 55 bars respectively.

## Invalidation

Any candle body crossing the line inside the anchor span.

## Python Module

patterns/three_point_trendline_support.py

------------------------------------------------------------------------

# PATTERN_005 Three Point Trendline Resistance

## Market Logic

Repeated rejection from a descending price boundary shows that sellers still
defend progressively lower prices. Upper-shadow crossings represent liquidity
tests and do not invalidate the boundary; body crossings mean price was
accepted through it and invalidate the candidate.

## Geometry

-   Exactly 3 selected swing-high anchors, while one line may have more contacts
-   P1 \> P2 \> P3 (negative slope)
-   P1-P3 \>= 40 complete bars
-   P1-P2 \>= 10 complete bars
-   P2-P3 \>= 10 complete bars

## Detection Rules

-   Evaluate all swing-high combinations; the three points need not be consecutive.
-   The middle swing high must fit the P1-P3 line within the configured ATR tolerance.
-   At each anchor the line must pass through the upper shadow or touch the open.
-   No non-anchor candle body may be crossed between P1 and P3.
-   Any number of upper shadows may cross the line.
-   Candle timestamps are opening timestamps; rules are identical for 15m, 1h, and 4h.
-   Prefer the longest span, then the smallest fit error.

## Required Features

-   anchor_count
-   touch_count
-   line_span
-   leg_1_span
-   leg_2_span
-   line_slope
-   line_angle
-   fit_error_atr
-   body_violation_count
-   upper_shadow_cross_count
-   open_touch_count
-   valid_triplet_count

## Factor Mapping

ThreePointTrendlineResistanceScore

## Invalidation

Any candle body crossing the line inside the anchor span.

## Python Module

patterns/three_point_trendline_resistance.py

------------------------------------------------------------------------

# PATTERN_006 Horizontal Resistance

## Market Logic

Two widely separated swing highs rejected from one horizontal price level show
repeated seller defense. Requiring all intervening highs below the level avoids
mistaking an already penetrated price zone for intact resistance. The separate
open-price ceiling rejects periods where value was accepted above either
anchor's opening price even if the wick rule still appears valid.

## Geometry

-   Two confirmed swing-high anchors
-   One shared horizontal level touching each anchor open or upper shadow
-   P1-P2 \>= 40 complete bar intervals
-   Every intervening high \<= the horizontal level
-   Every intervening open \<= min(P1 open, P2 open)

## Detection Rules

-   Evaluate all confirmed swing-high combinations, not only consecutive highs.
-   Use the same bar-count rule for 15m, 1h, and 4h input.
-   Allow equality as a touch; reject a high strictly above the level.
-   Rank valid candidates by span, then minimum anchor overshoot.
-   Emit only after the second swing high's right-side window is confirmed.

## Required Features

-   span
-   anchor_overshoot_atr
-   penetration_count
-   open_violation_count
-   intermediate_touch_count
-   intermediate_clearance_atr
-   intermediate_open_margin_atr
-   open_anchor_count
-   upper_shadow_anchor_count
-   confirmation_lag

## Factor Mapping

HorizontalResistanceScore

## Invalidation

Any intervening high above the level, or any intervening open above the lower
anchor open.

## Python Module

patterns/horizontal_resistance.py

------------------------------------------------------------------------

# PATTERN_007 Inverse Head and Shoulders

## Market Logic

After an established decline, the left shoulder marks an initial liquidity low.
The head makes a deeper low as sellers attempt continuation, but the right
shoulder holds near the left-shoulder price. This failure to create another low
shows selling exhaustion. A subsequent close above the neckline confirms that
buyers have accepted price above the intervening supply boundary.

## Geometry

-   Three confirmed swing lows ordered left shoulder, head, right shoulder
-   Left-shoulder to right-shoulder span \>= 40 complete bar intervals
-   Each shoulder-to-head leg \>= 10 bars
-   Head below both shoulders by at least 0.5 ATR
-   Shoulder price difference \<= 1.0 ATR
-   One confirmed swing high in each leg forms the neckline
-   Each neckline high is at least 5 bars from its adjacent lows

## Detection Rules

-   Evaluate all confirmed swing-low combinations; lows need not be consecutive.
-   The head must be the lowest traded price between both shoulders.
-   The left shoulder must be a new 40-bar low, preserving the preceding-decline context.
-   The right shoulder must be the lowest pullback after the right neckline high.
-   Rules use identical bar counts for 15m, 1h, and 4h data.
-   A confirmed right swing detects the structure without future bars.
-   A close above the projected neckline within 40 bars sets `breakout_confirmed`.
-   Rank confirmed breakouts first, then shoulder alignment, duration symmetry,
    head depth, span, and recency.

## Required Features

-   span
-   left_leg_span
-   right_leg_span
-   shoulder_price_error_atr
-   head_depth_atr
-   head_extreme_error_atr
-   duration_asymmetry
-   neckline_slope_atr_per_bar
-   prior_decline_atr
-   breakout_confirmed
-   breakout_distance_atr
-   breakout_volume_ratio
-   confirmation_lag
-   valid_candidate_count

## Factor Mapping

InverseHeadShouldersScore

## Invalidation

-   Head is not the unique structural low between the shoulders.
-   Right shoulder breaks below the ATR shoulder-alignment tolerance.
-   No confirmed neckline high exists in either leg.
-   A structure can remain detected but unconfirmed until the neckline is broken.

## Python Module

patterns/inverse_head_shoulders.py

------------------------------------------------------------------------

# PATTERN_008 Head and Shoulders Top

## Market Logic

After an established advance, the left shoulder marks an initial supply
rejection. The head retests liquidity at a higher price, but buyers cannot hold
the expansion. A right-shoulder rebound near the left shoulder then fails to
make a meaningful new high. A close below the neckline confirms price
acceptance beneath the intervening demand boundary.

## Geometry

-   Three confirmed swing highs ordered left shoulder, head, right shoulder
-   Left-shoulder to right-shoulder span \>= 40 complete bar intervals
-   Each shoulder-to-head leg \>= 10 bars
-   Head above both shoulders by at least 0.5 ATR
-   Shoulder price difference \<= 1.0 ATR
-   Selected head within 0.1 ATR of the absolute head-zone high
-   One confirmed swing low in each leg forms the neckline
-   Each neckline low is at least 5 bars from its adjacent highs

## Detection Rules

-   Evaluate raw confirmed swing highs so repeated head-zone tests remain visible.
-   The left shoulder must be a new 40-bar high, preserving the preceding advance.
-   The right shoulder must be the highest rebound after the right neckline low.
-   Treat highs within 0.1 ATR as one head liquidity zone; prefer time symmetry.
-   Use identical bar-count rules for 15m, 1h, and 4h input.
-   Confirm the structure only after the right swing's right-side window exists.
-   A close below the projected neckline within 40 bars sets `breakdown_confirmed`.
-   Rank confirmed breakdowns first, then shoulder alignment, duration symmetry,
    head height, span, and recency.

## Required Features

-   span
-   left_leg_span
-   right_leg_span
-   shoulder_price_error_atr
-   head_height_atr
-   head_extreme_error_atr
-   duration_asymmetry
-   neckline_slope_atr_per_bar
-   prior_advance_atr
-   breakdown_confirmed
-   breakdown_distance_atr
-   breakdown_volume_ratio
-   confirmation_lag
-   valid_candidate_count

## Factor Mapping

HeadAndShouldersTopScore

## Invalidation

-   Head zone does not stand at least 0.5 ATR above both shoulders.
-   Right shoulder exceeds the ATR shoulder-alignment tolerance.
-   No confirmed neckline low exists in either leg.
-   A structure remains unconfirmed until price closes below its neckline.

## Python Module

patterns/head_shoulders_top.py
