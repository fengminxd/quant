# FEATURES.md

# Feature Engineering Library

## Purpose

Reusable quantitative features shared by all patterns.

  Feature               Description              Formula Idea
  --------------------- ------------------------ -------------------------
  trend_angle           Trend slope              Linear regression slope
  line_span             Trendline length         bars(P1,Pn)
  touch_count           Trendline touches        Count of valid touches
  fit_error             Line fitting error       Mean distance to line
  atr_distance          Distance / ATR           abs(price-line)/ATR
  break_count           Trendline breaks         Confirmed breaks
  trend_strength        Trend quality            HH/HL + EMA slope
  volume_ratio          Relative volume          volume/MA(volume)
  atr_compression       Volatility contraction   ATR/ATR_MA
  breakout_strength     Breakout quality         close-resistance
  resistance_flatness   Flatness score           Std(highs)
  higher_low_score      Rising lows score        Regression on lows
  regression_line       Fitted boundary          Least-squares slope/intercept/RMSE
  triangle_convergence  Boundary compression     (initial gap-final gap)/initial gap
  market_structure      HH/HL or LH/LL            Confirmed swing comparisons
  ema99_context         Accepted-value context    Price/slope/persistence vs EMA99
  prior_level_state     Breakout/breakdown         Close and wick distance / ATR
  candle_rejection      Hammer geometry            Body and shadow proportions
  shared_anchor         Pattern confluence          Same right-anchor index
  resistance_reclaim   Old resistance accepted     (event close-level)/ATR
  confirmation_lag     Causal availability          confirmed_at-event index
  neckline_source      Cross-pattern lineage        Horizontal source in neckline
  retest_anchor        Cross-pattern lineage        Retest equals trendline P1
  support_lineage      Sequential structure          Both index links confirmed

## Rules

1.  Every feature must be deterministic.
2.  No future data.
3.  Unit tested.
4.  Independent from trading signals.
5.  Reusable by multiple patterns.

## Output

Every feature returns:

``` python
{
    "name": "...",
    "value": float,
    "confidence": float
}
```
