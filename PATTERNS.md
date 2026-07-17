# PATTERNS.md

# Price Action Pattern Library

## Purpose

Define chart patterns in a machine-readable specification.

## Timeframe Levels and Structure Search

The production structure scale is defined by complete K-line intervals, not by
wall-clock labels alone:

-   A tradable structure spans 40-160 intervals on its owning level.
-   Trading levels are ordered `15m -> 1h -> 4h`.
-   A `15m` span above 160 is promoted by elapsed time to `1h`; if the
    normalized `1h` span is still above 160, it is promoted again to `4h`.
-   A `1h` span above 160 is promoted to `4h`.
-   `1d` is collected only for higher-timeframe trend context. It is not a
    pattern-search or trade-entry level, so a `4h` structure above 160 does not
    become a tradable daily structure.

`PatternDetector.poll()` applies the three trading levels to every latest-bar
polling pass. Each detector sees only the trailing 161 visible bars, and the
polling layer rejects any detected anchor geometry outside 40-160 intervals.
`poll_at()` freezes the same window at a historical index for walk-forward and
rolling tests. Pattern modules retain raw `detect()` as a research API; live
and backtest trading decisions must use the constrained polling API.

The market-behavior interpretation is scale continuity: once a structure is
too wide for its current auction horizon, its information belongs to the next
higher aggregation rather than remaining a slow, stale low-timeframe setup.
Daily direction may gate or score a lower-timeframe setup, but cannot create an
entry by itself.

After detection, `PatternTradeFeasibilityScorer` may derive a structural stop,
price-action target, and cost-adjusted net reward/risk. This is a separate
score-only feasibility layer: it cannot change whether a Pattern exists and
cannot emit a trade signal. Triangle and head-and-shoulders structures remain
inactive there until their boundary or neckline confirmation occurs.

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

-   The fitted upper boundary has 2 or 3 independent confirmation clusters
-   The fitted lower boundary has 2 or 3 independent confirmation clusters
-   At least one boundary has 3 confirmations; the 2+2 combination is invalid
-   Selected confirmations alternate upper/lower; repeated same-side contacts
    without an intervening opposite-boundary confirmation are alternatives for
    one market leg, not independent confirmations
-   Upper slope is horizontal or negative
-   Lower slope is horizontal or positive
-   The two fitted boundaries overlap for at least 5 bars
-   Boundary distance contracts by at least 5%
-   Parallel horizontal boxes and diverging boundaries are rejected

## Detection Rules

-   Cluster nearby same-side pivots before fitting. Pivots no more than 5
    complete intervals apart form one confirmation cluster.
-   A nearby qualifying shadow contact may represent the cluster's first touch,
    but additional shadows in that cluster are contact evidence rather than new
    independent confirmations.
-   A recent closed upper- or lower-shadow contact may provide the latest
    boundary confirmation immediately at that close; it does not wait for a
    right-side Swing window. The post-Pattern factor separately checks any
    directional EMA99 rejection. Later Swing confirmation only strengthens the
    geometric evidence.
-   Evaluate all 2-point and 3-point combinations among the latest 12 clustered
    highs/lows, then reject every 2+2 boundary pair.
-   Each boundary spans at least 5 complete bar intervals.
-   Boundary regression RMSE must be no more than 0.5 ATR.
-   A normalized slope within +/-0.02 ATR per bar is treated as horizontal.
-   No confirmed swing within its boundary's own anchor span may violate that
    boundary by more than 0.25 ATR.
-   Prefer the latest active structure, then overlap span, confirmation count,
    fit, convergence, and total span.
-   Score upside breakouts and downside breakdowns symmetrically.
-   Geometry determines `detected`; the score remains an independent quality
    measure and `quality_threshold_passed` records whether it reaches 50.

## Required Features

-   upper_slope_atr_per_bar
-   lower_slope_atr_per_bar
-   upper_fit_error_atr
-   lower_fit_error_atr
-   upper_confirmation_count
-   lower_confirmation_count
-   boundary_confirmation_score
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

MUUSDT 4h from 2026-07-05 20:00 through 2026-07-15 08:00 UTC+8 is a
symmetrical converging triangle window. Its upper confirmations are 2026-07-05
20:00, 2026-07-09 20:00, and 2026-07-15 08:00; its lower confirmations are
2026-07-08 16:00 and 2026-07-13 20:00. Nearby same-boundary shadows are folded
into those confirmation clusters rather than counted as separate anchors. The
selected anchors span 57 complete intervals and the third upper anchor has a
high of 1006.18 and close of 1000.30. Its closed upper-shadow contact is
actionable immediately rather than waiting two more 4h bars. At that close
EMA99 is 1001.2692268: the upper shadow trades above EMA99 while the body and
close remain below it. The preceding decline is measured from the 2026-06-25
20:00 high to the first triangle anchor at 16.23 ATR. Prior lower highs, price
acceptance below a falling EMA99, and 31.17% boundary compression produce a
`TriangleBearishContinuationScore` of 76.3654. This activates a bearish trade
plan at the third upper close; a later downside break is confirmation rather
than an entry prerequisite.

NEARUSDT 4h from 2026-07-01 08:00 through 2026-07-17 16:00 UTC+8 is an
ascending triangle with three lower confirmations at 2026-07-01 08:00,
2026-07-13 12:00, and the final closed lower-shadow contact at 2026-07-17
16:00. The canonical upper confirmations are 2026-07-03 20:00 and 2026-07-15
20:00; 2026-07-07 00:00 is also a valid alternative first upper contact. The
two early upper wicks belong to the same market leg because no lower-boundary
confirmation separates them, so they are not counted together as two
independent confirmations. The selected anchors span 98 complete intervals.

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

# PATTERN_004 Horizontal Support

## Market Logic

Horizontal support represents either repeated defense of the same lower price
or a market-behavior transition in which former resistance is accepted above
and later holds as support. The second rule distinguishes pre-breakout trading
below resistance from post-breakout failure; only the latter invalidates the
retest hypothesis.

## Geometry

-   Two confirmed swing anchors separated by at least 40 bars
-   Double-low rule: aligned low/close support contacts
-   Breakout-retest rule: earlier high/open resistance aligned with a later
    swing-low/close support contact

For the double-low rule, every non-anchor candle between the two support
anchors must close strictly above the matched common support level. This rule
does not use ATR tolerance for an intervening close at or below that level.
The price-alignment tolerance is frozen at the right Swing Low's own causal ATR
so later confirmation candles cannot alter already-observed anchor geometry.

BTCUSDT 1h provides a reference double-bottom support case from
2026-06-25 21:00 to 2026-07-01 09:00 UTC+8. The confirmed Swing Lows are
58,030.0 and 57,758.6, yielding a common support level of 57,894.3 across 132
complete bars. The lowest intermediate close is 58,356.2, strictly above the
common support. The second Swing Low is confirmed at 2026-07-01 14:00 after
five right-side bars; the structural score is 96.7440.

## Breakout-Retest Rules

-   Find an accepted close above the aligned resistance after the first anchor.
-   Ignore below-resistance trading before that accepted breakout.
-   After breakout, closes must hold the level within ATR tolerance.
-   Allow at most one intermediate body interaction with the level.
-   The retest close must hold within the configured ATR tolerance; a marginal
    close below the exact midpoint remains a valid level-zone retest.
-   Prefer the most recent eligible broken resistance for a retest event.
-   `detect_at()` constrains the right anchor to a supplied event index.

## Required Features

-   rule_type
-   span
-   level
-   level_error_atr
-   breakout_index
-   retest_close_distance_atr

## Invalidation

Post-breakout close acceptance below the reclaimed level or repeated body
crossings before the retest.

## Python Module

patterns/horizontal_support.py

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
-   Keep Swing denoising independent from the 10-bar anchor-spacing rule.
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

## Reference Case

BTCUSDT 4h forms a three-point descending resistance through 2026-05-06 16:00,
2026-05-11 04:00, and 2026-05-15 00:00 UTC+8. The Swing Highs are 82,828.7,
82,460.5, and 81,999.0. The anchors span 27 and 23 bars, for a 50-bar total
span; the line slope is -16.594 per 4h bar. The third anchor is causally
confirmed at 2026-05-15 08:00. Fit error is 0.0285921 ATR, no non-anchor body
crosses the line, and the structural score is 94.2852.

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
open-price check records whether value was accepted above the resistance level;
an anchor's opening price is not itself the resistance boundary.

## Geometry

-   Two confirmed swing-high anchors
-   One shared horizontal level touching each anchor open or upper shadow
-   P1-P2 \>= 40 complete bar intervals
-   Every intervening high \<= the horizontal level
-   Every intervening open \<= the horizontal resistance level

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

## Reference Case

SOLUSDT 1h forms horizontal resistance between 2026-07-04 12:00 and
2026-07-07 05:00 UTC+8. The confirmed swing highs are 83.96 and 83.75, so the
shared upper-shadow contact level is 83.75. The anchors span 65 complete bars.
The maximum intervening high is 83.57 and the maximum intervening open is
83.44; neither trades above the resistance level. The second anchor is
causally confirmed after two right-side bars at 2026-07-07 07:00. Its
`HorizontalResistanceScore` is 81.4977.

## Invalidation

Any intervening high or open above the horizontal resistance level.

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

## Reference Case

ZECUSDT 1h, UTC+8 from 2026-06-25 21:00 through 2026-07-01 09:00:

-   left shoulder: 2026-06-25 21:00 at 386.01;
-   head: 2026-06-29 06:00 at 367.77;
-   right shoulder: 2026-07-01 09:00 at 385.07;
-   neckline highs: 2026-06-27 00:00 at 429.25 and
    2026-06-30 06:00 at 413.98;
-   the right shoulder is observable after five confirmation bars;
-   the projected neckline breakout is confirmed at 2026-07-01 21:00.

On the Binance USD-M production feed configuration—5-left/5-right pivots and
one-hour opening timestamps—the raw ZECUSDT structural and breakout
score is 90.8737. The offline regression fixes the reported shoulder/head
timestamps and verifies a detected, breakout-confirmed structure without
network access.

The same left-neckline candle at 2026-06-27 00:00 later becomes the source of
a breakout-retest horizontal support at 2026-07-03 12:00. That retest is the
first supplied anchor of a rising support line completed by 2026-07-06 20:00
and 2026-07-07 12:00. The last supplied contact maps to the adjacent confirmed
Swing Low at 13:00 with a one-bar offset and only 0.07 price difference.

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

## Reference Case Audit

SOLUSDT 1h, UTC+8 from 2026-07-09 09:00 through 2026-07-11 23:00
contains the reported local top and right-shoulder EMA99 rejection. On the
Binance USD-M feed, the 2026-07-11 23:00 right-shoulder candle is O=78.44,
H=78.86, C=78.34 and the causal EMA99 is 78.55594103 after warm-up from
2026-05-01. Its whole candle body remains below EMA99 while the upper shadow
trades through it. The strict geometry is:

-   left shoulder: 2026-07-09 15:00 at 78.82;
-   head: 2026-07-10 18:00 at 79.64;
-   right shoulder: 2026-07-11 23:00 at 78.86;
-   neckline lows: 2026-07-09 20:00 at 77.20 and
    2026-07-11 09:00 at 77.42.

The 23:00 right shoulder and EMA99 rejection are observable at that candle's
close, but the strict Swing anchor becomes causally confirmed at 2026-07-12
04:00 after five right-side bars, with a structure score of 81.9820. A close
below the projected neckline at 2026-07-12 07:00 raises the confirmed score to
96.9820. The regression preserves the distinction between the right-shoulder
event time and its later Swing confirmation time.
This is a bounded research-window result. With the full trailing 161-bar
production history, the left shoulder is not a new 40-bar high and an earlier
already-confirmed top is selected; the reported local structure therefore does
not replace the active production candidate under the current ranking rules.

## Invalidation

-   Head zone does not stand at least 0.5 ATR above both shoulders.
-   Right shoulder exceeds the ATR shoulder-alignment tolerance.
-   No confirmed neckline low exists in either leg.
-   A structure remains unconfirmed until price closes below its neckline.

## Python Module

patterns/head_shoulders_top.py
