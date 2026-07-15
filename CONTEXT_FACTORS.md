# Pattern-Conditioned Context Factors

## Purpose

Context factors are evaluated only after one of the configured price-action
patterns has been detected. They add evidence to a pattern-quality score; they
never emit Buy or Sell.

The supported gates are:

-   PATTERN_003 Three Point Trendline Support
-   PATTERN_004 Horizontal Support
-   PATTERN_005 Three Point Trendline Resistance
-   PATTERN_006 Horizontal Resistance
-   PATTERN_007 Inverse Head and Shoulders
-   PATTERN_008 Head and Shoulders Top

## Evaluation Flow

``` text
closed bars through t
        ↓
configured Pattern.detect()
        ↓ detected only
ContextFeatureExtractor
        ↓
selected 0-100 context factors
        ↓ pattern-specific polarity and fixed weights
Pattern Context Composite Score
```

`PatternContextScorer.evaluate()` slices the bars through `as_of_index` before
running the pattern detector. This is the preferred walk-forward API because
neither the pattern nor its context factors can see later bars.

`PatternContextScorer.score()` accepts an existing `PatternResult`; callers are
responsible for ensuring that result was produced from the same visible window.

## Shared Features

### Market Structure

-   higher_high_ratio
-   higher_low_ratio
-   lower_high_ratio
-   lower_low_ratio
-   trend_efficiency_signed
-   trend_comparison_count

Only confirmed pivots from the shared Swing module are used.

### EMA99 Context

-   ema99_value
-   ema99_distance_atr
-   ema99_slope_atr
-   ema99_above_close_ratio

EMA99 is a causal proxy for longer-horizon accepted value. It remains inactive
until 99 bars are available and never acts as a direct trading rule.

### Prior Swing Levels

-   prior_swing_high
-   prior_swing_low
-   breakout_close_distance_atr
-   breakout_high_distance_atr
-   breakdown_close_distance_atr
-   breakdown_low_distance_atr

A wick through a level followed by a close back inside is represented as a
false breakout or false breakdown rather than accepted price transition.

### Latest Closed Candle

-   body_ratio
-   lower_shadow_ratio
-   upper_shadow_ratio
-   lower_shadow_body_ratio
-   upper_shadow_body_ratio
-   body_bottom_location
-   body_top_location
-   close_location
-   range_atr_ratio

## Factors

### UptrendStructureScore

Scores higher highs, higher lows, and positive path efficiency. It becomes an
active condition only when enough confirmed swing comparisons exist and the
score is at least 60.

### DowntrendStructureScore

Mirrors the uptrend factor through lower highs, lower lows, and negative path
efficiency.

### EMA99ContextScore

Uses a bullish 0-100 axis:

-   Above a rising EMA99 with persistent closes above it: greater than 50.
-   Below a falling EMA99 with persistent closes below it: less than 50.
-   Neutral or incomplete warmup: effectively 50 in the composite.

Bearish pattern profiles reverse this axis during aggregation.

### PriorHighBreakoutScore

Scores close acceptance above the latest confirmed swing high using ATR
distance, close location, and bullish body expansion. A wick-only penetration
produces a score below 50 and state `false_breakout`.

### PriorLowBreakdownScore

Mirrors the breakout factor below the latest confirmed swing low. A wick-only
penetration and reclaim produces state `false_breakdown`.

### HammerScore

Scores small-body, dominant lower-shadow rejection geometry. It is active when:

-   body ratio is between 0.03 and 0.35;
-   lower shadow is at least twice the body;
-   upper shadow is no more than 10% of the candle range;
-   the body is in the upper 40% of the candle.

### InvertedHammerScore

Mirrors HammerScore using a dominant upper shadow and a body in the lower 40%
of the candle. At an established resistance this geometry represents upper
price rejection and has shooting-star market semantics; the factor name only
describes its candle geometry.

## Pattern Profiles

| Pattern | Pattern | Up | Down | EMA99 | High break | Low break | Hammer | Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Three-point support | 35% | +10% | -10% | +10% | +15% | -15% | +5% | — |
| Horizontal support | 35% | +10% | -10% | +10% | +15% | -15% | +5% | — |
| Three-point resistance | 35% | -10% | +10% | -10% | -15% | +15% | — | +5% |
| Horizontal resistance | 35% | -10% | +10% | -10% | -15% | +15% | — | +5% |
| Inverse head-and-shoulders | 30% | +10% | -10% | +10% | +15% | -15% | +5% | +5% |
| Head-and-shoulders top | 30% | -10% | +10% | -10% | -15% | +15% | +5% | +5% |

`+` means the raw factor axis supports the pattern direction. `-` means the
axis is reversed as `100 - raw_score`.

## Inactive Conditions

Configured but inactive conditions contribute a fixed neutral score of 50.
Weights are never renormalized around the active conditions. This prevents a
pattern with one active high-scoring condition from becoming artificially
stronger than a fully evaluated pattern.

The composite result exposes:

-   selected_factors
-   active_factors
-   raw factor scores
-   direction-adjusted effective scores
-   weights and polarities
-   factor-coverage confidence
-   as_of_index

## Validation

Each profile must be tested incrementally:

1.  Pattern quality alone.
2.  Pattern plus market structure.
3.  Add EMA99 context.
4.  Add prior-level transition.
5.  Add latest-candle rejection.

Report forward-return IC and RankIC, score-bucket monotonicity, walk-forward and
rolling out-of-sample results, fees, slippage, funding, Sharpe, Sortino, maximum
drawdown, profit factor, win rate, trade count, and Monte Carlo resampling.

Correlated evidence must be monitored explicitly: trend structure, EMA99, and
prior-level breakout may describe overlapping price behavior. A factor stays in
a production profile only if it adds stable out-of-sample information.
