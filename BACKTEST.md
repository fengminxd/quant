# Pattern Anchor Outcome Audit

## Purpose

`AnchorTradeOutcomeEvaluator` evaluates the standard report's initial stop,
1.5% profit lock, and 3% final target from the first causal structure-zone
reclaim after each historical Pattern is detected.
It is a research/backtest audit and never emits a live Buy/Sell signal.

## Entry Mapping

| Pattern | Direction | Structure zone |
|---|---|---|
| PATTERN_004 horizontal support | Bullish | Second anchor |
| PATTERN_006 horizontal resistance | Bearish | Second anchor, FIXED_COMBO_002 only |
| PATTERN_007 inverse head-and-shoulders | Bullish | Right shoulder |
| PATTERN_003 three-point support | Bullish | Third anchor |
| PATTERN_002 frozen uptrend | Bullish | Third lower-boundary anchor |
| PATTERN_002 frozen downtrend | Bearish | Third upper-boundary anchor |

`PATTERN_001`, `PATTERN_005`, and `PATTERN_008` implementations are retained
for research but are disabled in every trading and report cohort.
`PATTERN_006` is rejected as a standalone event; only a PATTERN_006 event
labeled `FIXED_COMBO_002` may use the second-anchor entry. Its
horizontal-resistance matcher remains available as component evidence for
`FIXED_COMBO_004` and `FIXED_COMBO_008`; FIXED_COMBO_004 is research-only
because its PATTERN_008 parent is disabled.

Triangle trend is frozen at the earliest boundary anchor and uses the same
directional structure gate as fixed priority combinations. A triangle without
the required trend and third boundary anchor is reported as ineligible.
Head-and-shoulders entries use the right-shoulder zone, not the neckline.

## Barrier and OHLC Semantics

- Scanning begins on the first closed candle after Pattern detection.
- A candidate candle must overlap the structure zone and close back on the
  trade side of the structure level.
- Default zone width is 0.25 ATR, maximum close distance is 0.35 ATR, and the
  standard setup expires after eleven waiting candles.
- Entry price is the qualifying candle close; the geometry anchor remains
  recorded as `structure_anchor`.
- Outcome inspection begins on the next candle.
- Default bullish stop/lock/final target: entry × 0.985 / entry × 1.015 /
  entry × 1.03.
- Default bearish stop/lock/final target: entry × 1.015 / entry × 0.985 /
  entry × 0.97.
- Stop-loss, profit-lock, and final-target ratios are configurable.
- Reaching 1.5% profit records the trigger and activates the stop at that same
  1.5% profit price from the next candle.
- On the trigger candle, an initial-stop touch wins conservatively. Once the
  lock is active, a same-candle protected-stop/final-target touch closes at
  the protected stop because intrabar order is unknown.
- Cases with neither barrier touched by the final database candle remain
  unresolved and stay in the total-case denominator.
- Default net-return estimates include a 0.02% entry fee, 0.05% exit fee,
  and 0.02% slippage per side; barrier-touch classification itself remains
  at the configured gross prices.

## Causality Boundary

Pattern geometry may still be confirmed after its historical structure
anchor, but no entry is backfilled to that anchor. Every plan exposes the
structure confirmation lag, `entry_wait_bars`, `entry_quality_score`, and
`causal_at_entry`. Outcome inspection begins on the candle after entry.

## Cohorts

The report gives:

- percentages over all eligible cases, including unresolved cases;
- percentages over resolved cases only;
- a separate FIXED_COMBO subset;
- full initial-stop, protected-profit, final-target, unresolved, and
  ineligible case lists.

## Aggressive Confirmed-Pivot Entries

The aggressive report uses an independent scanner. Its requested final
reference anchor must survive the Pattern's right-side Pivot Low/Pivot High
window before an order may become active. Pattern geometry is first evaluated
at the anchor close, but no entry is permitted until that pivot is causally
confirmed.

Reference anchors are horizontal support/resistance P2, inverse/top
head-and-shoulders right shoulder, three-point support P3, or the
trend-selected triangle boundary P3. Triangle trend is frozen at its earliest
boundary anchor: uptrend selects lower P3 for a buy and downtrend selects upper
P3 for a sell.

- Buy reference price: use the anchor low when its lower shadow is no longer
  than its body. When the lower shadow is longer, use the open of a bullish
  anchor or the close of a bearish anchor (the candle-body low).
- Sell reference price: use the anchor high when its upper shadow is no longer
  than its body. When the upper shadow is longer, use the close of a bullish
  anchor or the open of a bearish anchor (the candle-body high).
- A doji uses its low for a buy and its high for a sell.
- An exact shadow/body length tie uses the entry-side extreme (low for buy,
  high for sell).
- The reference limit is active on the next six candles after pivot
  confirmation. A buy fills when
  `low <= reference`; a sell fills when `high >= reference`.
- No fill by the sixth close expires the setup.
- Exit inspection starts on the candle after the fill, avoiding unknown
  fill-candle intrabar ordering.

## One-command research bundle

Generate the rule-details PDF, anchor trade report, and continuous
trade-point candlestick overview from one identical candle cohort:

```bash
.venv/bin/python -m research.run_trade_bundle \
  --symbol BTC \
  --timeframe 1h \
  --start "2026-04-15 12:00" \
  --end "2026-07-20 12:00" \
  --stop-loss-pct 1.0 \
  --lock-profit-pct 1.5 \
  --take-profit-pct 3.0 \
  --entry-fee-pct 0.02 \
  --exit-fee-pct 0.05
```

`--start` and `--end` are inclusive candle-open times in UTC+8. They must
align to the requested candle boundary and may not include an unclosed candle.
The default output directory includes the requested range so separate runs do
not overwrite each other. It also includes the exit configuration:
`logs/<symbol>_<timeframe>_trade_bundle/<start>_<end>_sl<SL>_lock<LOCK>_tp<TP>/pdf`.
An alternative directory can be selected with `--output-dir`.

`--stop-loss-pct`, `--lock-profit-pct`, and `--take-profit-pct` are
percentages. They default to `1.5`, `1.5`, and `3.0`, respectively.
`--entry-fee-pct` and `--exit-fee-pct` are also percentages and default to
`0.02` and `0.05`, respectively. The aliases `--open-fee-pct` and
`--close-fee-pct` are accepted. One configured cost model is used by the
rule-details PDF notes, text outcome report, and trade-point PDF summary.

The three output names are:

- `<SYMBOL>_<TIMEFRAME>_规则明细.pdf`
- `<SYMBOL>_<TIMEFRAME>_开单报告.txt`
- `<SYMBOL>_<TIMEFRAME>_开单点K线总览.pdf`

Trade bundles support `15m`, `1h`, and `4h`. Daily candles remain HTF
trend-context data and cannot directly produce trading Patterns.
