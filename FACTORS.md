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

# FACTOR_002 TriangleScore

## Market Logic

Reliable triangles have well-fitted inward boundaries, measurable gap
contraction, and preferably volatility/volume compression or an accepted
breakout through either side.

## Inputs

-   boundary_direction_score
-   boundary_confirmation_score
-   boundary_fit_score
-   convergence_score
-   atr_compression
-   volume_contraction
-   breakout_strength

## Formula

``` text
0.10*boundary_direction
+0.10*boundary_confirmation
+0.20*boundary_fit
+0.20*convergence
+0.15*atr_compression
+0.10*volume_contraction
+0.15*breakout_strength
```

`boundary_confirmation_score` is 100 for a 3+3 structure and 80 for either
3+2 or 2+3. A 2+2 structure is invalid and never reaches factor calculation.

## Output

0\~100

## Validation

-   Walk-forward
-   Out-of-sample
-   Transaction cost
-   Profit factor

------------------------------------------------------------------------

# FACTOR_002A TriangleBearishContinuationScore

## Market Logic

A converging triangle is direction neutral by itself. It becomes a bearish
continuation candidate when it pauses an established decline, price remains
accepted below a falling EMA99, and the third upper-boundary candle probes
above EMA99 only through its upper shadow before closing back below it. This
models failed acceptance at dynamic supply rather than an indicator crossover.

## Inputs

-   prior_lower_high_ratio
-   prior_lower_low_ratio
-   prior_decline_atr
-   prior_trend_efficiency_signed
-   prior_ema99_distance_atr
-   prior_ema99_slope_atr
-   prior_ema99_above_close_ratio
-   upper_third_high_above_ema_atr
-   upper_third_close_below_ema_atr
-   upper_third_ema_wick_rejection
-   triangle_compression_ratio

## Formula

``` text
0.25*prior_structure
+0.30*prior_ema_trend
+0.30*upper_ema_rejection
+0.15*triangle_compression
```

## Output

0-100 score. An active score identifies
`bearish_continuation_entry_candidate`: the established decline plus the third
upper-boundary EMA99 wick rejection is sufficient to activate a bearish trade
plan. A downside boundary break is subsequent confirmation, not an entry
prerequisite. The factor remains score-only and does not itself emit Sell.

## Validation

-   Forward-return IC and RankIC after triangle confirmation
-   Separate pending candidates from accepted downside breaks
-   Walk-forward/OOS by timeframe and market regime
-   Fee, slippage, funding, and false-break sensitivity

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

Longer-lived, closely aligned resistance with clean price clearance and
intervening opens farther below the actual resistance level is stronger
evidence of persistent seller defense.

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

Seven pattern-conditioned context factors and their six Pattern profiles are
specified in `CONTEXT_FACTORS.md`.

------------------------------------------------------------------------

# FACTOR_006 BullishSupportConfluenceScore

## Market Logic

When an ascending three-point support and a reclaimed horizontal resistance
share the same third-point candle, two distinct buyer behaviors overlap:
progressively higher liquidity defense and acceptance above an old supply
level. A close above that reclaimed level and above EMA99 adds event-time
confirmation without turning EMA into a standalone entry rule.

## Gate

-   Both support patterns are detected at the same right anchor.
-   The third-point close is above the reclaimed resistance.
-   The third-point close is above a fully warmed EMA99 context.
-   The score becomes available only after the third swing is confirmed.

## Inputs and Formula

``` text
0.30*three_point_trendline_quality
+0.25*horizontal_retest_quality
+0.25*resistance_reclaim_quality
+0.20*ema99_context_quality
```

The detector may consume the right-side swing-confirmation bars, but every
context input is frozen at the third-point close. Output is a 0-100 score only.

## Reference Validation

The offline HYPE 1h fixture uses the reported UTC+8 timestamps:

-   slope support: 2026-05-17 01:00, 2026-05-18 23:00,
    2026-05-20 08:00;
-   reclaimed resistance: 2026-05-18 05:00 to 2026-05-20 08:00.

It asserts shared-anchor confluence, resistance reclaim, close above EMA99,
two-bar swing confirmation lag, and a score of at least 80.

## Validation

-   Forward-return IC and RankIC by 15m, 1h, 4h, and 1d
-   Walk-forward and rolling out-of-sample score buckets
-   Fees, slippage, and funding sensitivity
-   Monte Carlo resampling and correlated-evidence ablation

------------------------------------------------------------------------

# SupportLineageScore

## Market Logic

A reversal pattern has stronger continuation evidence when one of its own
neckline anchors becomes a reclaimed horizontal support and that exact retest
then starts a rising three-point support line. Index lineage is mandatory so
unrelated high-scoring historical patterns cannot be combined.

## Gate

-   Horizontal-support source index belongs to the inverse-H&S neckline.
-   Horizontal retest index equals the first trendline anchor index.
-   All three patterns are independently detected and confirmed.

## Formula

``` text
0.30*inverse_head_shoulders_quality
+0.30*horizontal_retest_quality
+0.40*trendline_continuation_quality
```

If either index relationship fails, the factor returns zero. The ZECUSDT 1h
reference chain scores 91.7757 from component scores 90.8737, 88.1377, and
95.1807. Output remains a score only.

## Validation

-   Compare linked structures against randomly paired high-score patterns.
-   Measure incremental IC after controlling for each component score.
-   Use confirmation-time execution with fees, slippage, and funding.

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

------------------------------------------------------------------------

# FACTOR_007 ThreePointTrendlineSupportScore

## Market Logic

A longer, accurately fitted rising boundary with no body acceptance through it
is stronger evidence that buyers repeatedly defend progressively higher prices.

## Inputs

-   line_span
-   fit_error_atr
-   line_slope
-   body_violation_count

## Formula

``` text
0.25*span_quality
+0.25*fit_quality
+0.25*positive_slope
+0.25*body_integrity
```

## Output

0\~100 structural score; never Buy/Sell.

## Validation

-   Forward-return IC and RankIC by timeframe and market regime
-   Walk-forward and rolling out-of-sample tests
-   Fee, slippage, and funding sensitivity
-   Monte Carlo trade-order and execution-cost resampling

------------------------------------------------------------------------

# FACTOR_008 NetRewardRiskScore

## Market Logic

A valid chart pattern is not automatically a viable trade. After pattern
detection, the nearest structural invalidation and price-action target define
the payoff geometry. Execution and holding costs must then increase downside
risk and reduce upside reward before the setup is considered feasible.

## Pattern Gate and Default Plan

-   Trendline support/resistance: projected line stop and nearest confirmed
    opposing swing liquidity target.
-   Horizontal support/resistance: level-zone stop and nearest confirmed
    opposing swing liquidity target.
-   Triangle breakout: stop behind the broken boundary and target by initial
    triangle-height projection.
-   Bearish continuation triangle: the third upper-boundary wick rejection of
    EMA99 activates the plan without a lower-boundary break; stop beyond the
    upper boundary and target the contemporaneous lower boundary.
-   Inverse head-and-shoulders/head-and-shoulders top: activated only after
    neckline confirmation; stop beyond the right shoulder and target by the
    head-to-neckline measured move.
-   Default stop buffer is 0.20 ATR.

## Inputs

-   plan_available
-   entry_price
-   stop_price
-   target_price
-   gross_risk
-   gross_reward
-   net_risk
-   net_reward
-   gross_reward_risk
-   net_reward_risk
-   minimum_net_reward_risk
-   stop_distance_atr
-   target_distance_atr
-   estimated_cost_r

## Net Formula

``` text
net_risk = gross_risk + entry_cost + stop_exit_cost + funding_cost
net_reward = gross_reward - entry_cost - target_exit_cost - funding_cost
net_reward_risk = net_reward / net_risk
```

Default cost assumptions are configurable: 0.05% fee per side, 0.02% slippage
per side, and zero funding until a holding-period estimate is supplied.

## Score

``` text
net R <= 1.0  -> 0
net R = 1.5   -> 40
net R = 2.0   -> 70
net R >= 3.0  -> 100
```

Linear interpolation applies between knots. Feasibility is a separate gate:
1.8 net R for trendline rules and 2.0 net R for triangle, horizontal, and
head-and-shoulders rules. The factor never emits Buy/Sell.

## Validation

-   Compare gross-R and net-R cohort expectancy
-   Walk-forward and rolling OOS by pattern, timeframe, and market regime
-   Replay ambiguous stop/target bars on a lower timeframe
-   Fee, slippage, funding, and stop-gap sensitivity
-   MFE, MAE, time-to-target, Sharpe, Sortino, and maximum drawdown
