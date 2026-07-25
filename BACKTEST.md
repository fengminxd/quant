# Pattern Anchor Outcome Audit

## Purpose

`AnchorTradeOutcomeEvaluator` labels the requested ±1.5% outcomes for
historical PDF Pattern events. It is a research/backtest audit and never emits
a live Buy/Sell signal.

## Entry Mapping

| Pattern | Direction | Retrospective entry anchor |
|---|---|---|
| PATTERN_004 horizontal support | Bullish | Second anchor |
| PATTERN_006 horizontal resistance | Bearish | Second anchor |
| PATTERN_007 inverse head-and-shoulders | Bullish | Right shoulder |
| PATTERN_008 head-and-shoulders top | Bearish | Right shoulder |
| PATTERN_003 three-point support | Bullish | Third anchor |
| PATTERN_005 three-point resistance | Bearish | Third anchor |
| PATTERN_002 frozen uptrend | Bullish | Third lower-boundary anchor |
| PATTERN_002 frozen downtrend | Bearish | Third upper-boundary anchor |

Triangle trend is frozen at the earliest boundary anchor and uses the same
directional structure gate as fixed priority combinations. A triangle without
the required trend and third boundary anchor is reported as ineligible.

## Barrier and OHLC Semantics

- Entry price is the selected geometry-anchor price.
- Outcome inspection begins on the next candle.
- Default bullish stop/target: entry × 0.985 / entry × 1.015.
- Default bearish stop/target: entry × 1.015 / entry × 0.985.
- Stop-loss and take-profit ratios are independently configurable.
- The first touched barrier determines the outcome.
- If both barriers are touched in one OHLC candle, stop-loss wins
  conservatively because intrabar order is unknown.
- Cases with neither barrier touched by the final database candle remain
  unresolved and stay in the total-case denominator.
- Default net-return estimates include 0.05% fee and 0.02% slippage per side;
  barrier-touch classification itself remains at the requested gross ±1.5%.

## Causality Boundary

Most Swing-derived Patterns are confirmed after their historical anchor.
Therefore an entry filled at that past anchor is not a causally executable
signal. Every plan exposes `confirmation_delay_bars` and `causal_at_anchor`;
the text report prominently labels the results as retrospective.

For a production backtest, execute no earlier than the detection timestamp
and model whether a later limit order at the anchor price is actually filled.

## Cohorts

The report gives:

- percentages over all eligible cases, including unresolved cases;
- percentages over resolved cases only;
- a separate FIXED_COMBO subset;
- full stop-loss, take-profit, unresolved, and ineligible case lists.

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
  --take-profit-pct 3.0
```

`--start` and `--end` are inclusive candle-open times in UTC+8. They must
align to the requested candle boundary and may not include an unclosed candle.
The default output directory includes the requested range so separate runs do
not overwrite each other. It also includes the barrier configuration:
`logs/<symbol>_<timeframe>_trade_bundle/<start>_<end>_sl<SL>_tp<TP>/pdf`.
An alternative directory can be selected with `--output-dir`.

`--stop-loss-pct` and `--take-profit-pct` are percentages. Both default to
`1.5`, preserving the original symmetric ±1.5% outcome definition.

The three output names are:

- `<SYMBOL>_<TIMEFRAME>_规则明细.pdf`
- `<SYMBOL>_<TIMEFRAME>_开单报告.txt`
- `<SYMBOL>_<TIMEFRAME>_开单点K线总览.pdf`

Trade bundles support `15m`, `1h`, and `4h`. Daily candles remain HTF
trend-context data and cannot directly produce trading Patterns.
