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
- Bullish stop/target: entry × 0.985 / entry × 1.015.
- Bearish stop/target: entry × 1.015 / entry × 0.985.
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
