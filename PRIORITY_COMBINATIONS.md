# Fixed Priority Pattern Combinations

## Purpose

These combinations label unusually coherent price-action evidence after a
configured Pattern has been detected. They are fixed research cohorts on
`15m`, `1h`, and `4h`; they return a 0-100 coverage score and never emit
Buy/Sell.

EMA99 is calculated independently from the closed candles of the Pattern's own
timeframe. An EMA condition is unavailable until the anchor has 99 historical
candles. Lower or upper shadows may cross EMA99 because the rule constrains the
specified body price only.

## Fixed Profiles

| ID | Pattern gate | Conditions |
|---|---|---|
| FIXED_COMBO_001 | PATTERN_004 `double_swing_low` | Second anchor close above EMA99 |
| FIXED_COMBO_002 | PATTERN_006 | Second anchor open below EMA99 |
| FIXED_COMBO_003 | PATTERN_007 | Head close above EMA99; head forms prior double-bottom support |
| FIXED_COMBO_004 | PATTERN_008 | Head open below EMA99; head forms prior horizontal resistance |
| FIXED_COMBO_005 | PATTERN_003 | First anchor forms prior double bottom; all three anchor closes above EMA99; third anchor forms breakout-retest support |
| FIXED_COMBO_006 | PATTERN_005 | First anchor forms prior horizontal resistance; third anchor open below EMA99 |
| FIXED_COMBO_007 | PATTERN_002 upper 2/lower 3 + frozen uptrend | Lower P1 forms prior double bottom; lower P3 close above EMA99 |
| FIXED_COMBO_008 | PATTERN_002 upper 3/lower 2 + frozen downtrend | Upper P1 forms prior horizontal resistance; upper P3 open below EMA99 |

For FIXED_COMBO_005, “three anchor closes” means all three low anchors must
close above their respective causal EMA99 values.

## Historical-Level Semantics

The target anchor is supplied by the detected parent Pattern. It is compared
with earlier confirmed swings from the shared Swing module:

- Double bottom requires a real intersection between both anchors'
  close/lower-shadow zones, minimum 40-bar span, no intervening body pierce,
  and all intermediate closes above support. ATR cannot bridge a contact gap.
- Breakout-retest support requires a prior swing high, accepted close above
  the shared traded-price level, and closes holding that level into the
  explicit retest anchor. The prior open/upper-shadow zone must actually
  intersect the target close/lower-shadow zone; ATR cannot bridge a contact
  gap. Post-breakout holding uses a separate 0.1 ATR tolerance.
- Horizontal resistance requires a shared open/upper-shadow level and no
  intervening high or open above it. PATTERN_006 and fixed combinations call
  the same traded-zone intersection function; ATR and relative-price tolerance
  cannot bridge a gap.

This avoids reclassifying the parent anchor with a different future pivot
window.

## Triangle Trend Gate

The trend is frozen at the earliest triangle anchor. Only confirmed swings
known at that point are used:

- FIXED_COMBO_007 requires active HH/HL upward structure.
- FIXED_COMBO_008 requires active LH/LL downward structure.

Later triangle candles cannot alter this prior-trend observation.

## Score and Label

After Pattern, timeframe, variant, and trend gates pass:

``` text
coverage score = matched configured conditions / configured conditions * 100
priority_fixed_combination = matched condition count > 0
```

The result exposes the combination ID, matched conditions, condition count,
coverage score, anchor indexes, EMA values, level source indexes, and breakout
index where applicable. Historical scan de-duplication preserves priority
events ahead of non-priority events in the same nearby same-rule bucket.
Matched historical level relations retain their condition, source anchor,
target anchor, shared level, and support/resistance type. PDF event charts
state symbol, timeframe, Pattern rule, and all conditions actually combined.
They render support sources as `S`, resistance sources as `R`, connect each
source to its parent anchor at the shared level, and draw the same-timeframe
causal EMA99. Legacy source-only events remain visible as orange `L` anchors.

## Validation

Treat each ID and each condition-count tier as a separate cohort. Report
forward-return IC and RankIC, score-bucket monotonicity, walk-forward and
rolling out-of-sample results by `15m`, `1h`, and `4h`, fees, slippage,
funding, Sharpe, Sortino, maximum drawdown, profit factor, win rate, trade
count, and Monte Carlo resampling.
