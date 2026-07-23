# API

## Pattern

detect(data)-\>PatternResult extract_features(data)-\>dict
calculate_score(features)-\>float

PatternDetector.poll(data_by_timeframe)-\>list[PatternPollResult]

PatternDetector.poll_at(data, timeframe, as_of_index)-\>list[PatternPollResult]

`poll()` is the production structure-search entry point. It checks `15m`,
`1h`, and `4h` in order, excludes `1d`, supplies no more than 161 visible bars
(160 complete intervals), and emits only structures spanning 40-160 intervals.
`poll_at()` applies the same rule to a historical as-of index for no-look-ahead
backtests. `PatternPollResult.window_start_index` maps window-local pattern
geometry back to the source series.

The raw `detect()` method remains a timeframe-agnostic research primitive and
does not perform timeframe promotion or production window enforcement.

`Triangle.detect()` fits 2-point and 3-point boundaries after grouping nearby
same-side contacts into confirmation clusters. Valid confirmation combinations
are 3+3, 3+2, and 2+3; 2+2 is rejected before feature or factor calculation.
Selected confirmations must alternate between boundaries, and the latest
closed upper or lower wick may confirm its boundary without future bars.

## Timeframe Hierarchy

timeframe_level(timeframe)-\>TimeframeLevel

resolve_structure_span(timeframe, span_bars)-\>StructureSpanResolution

Trading levels are `15m`, `1h`, and `4h`; `1d` has the `trend_context` role.
Spans above 160 intervals are normalized by elapsed time and promoted through
the trading hierarchy. Promotion past `4h` terminates as non-tradable daily
trend context.

`MarketDataConfig.trading_timeframes` and `trend_timeframes` expose these roles
without preventing the collector from storing all four configured datasets.

bearish_triangle_continuation_features(data, pattern)-\>dict

TriangleBearishContinuationScore.calculate(features)-\>FactorResult

Triangle continuation context reads window-local anchors through
`window_start_index`, freezes prior trend at the first anchor, and freezes EMA99
rejection at the third upper anchor. Swing-confirmation bars may establish that
the anchor is a pivot but cannot change its feature values.

## Post-Pattern Trade Feasibility

PatternTradePlanExtractor.extract(pattern_result, data, as_of_index, plan)
    -\>tuple[PatternTradePlan | None, int, float]

trade_feasibility_features(plan, atr, minimum_net_reward_risk, costs)-\>dict

NetRewardRiskScore.calculate(features)-\>FactorResult

PatternTradeFeasibilityScorer.evaluate(pattern, data, as_of_index)
    -\>PatternTradeFeasibilityEvaluation

PatternTradeFeasibilityScorer.score(pattern_result, data, as_of_index, plan)
    -\>PatternTradeFeasibilityEvaluation

PatternTradeFeasibilityScorer.score_detected(pattern_results, data)-\>list

This layer runs after Pattern detection and does not change Pattern quality.
Default plans use structural invalidation and price-action targets; callers may
provide an explicit plan for execution-specific entry/retest logic. A triangle
may activate either on a boundary break or on an active bearish-continuation
context at the third upper EMA99 rejection; head-and-shoulders still requires
neckline confirmation. `as_of_index` truncation and polling-window offsets
preserve causal geometry. The result exposes `active`, `feasible`, cost
assumptions, and `emits_signal=False` metadata.

## Feature

compute(data)-\>FeatureResult

## Factor

calculate(features)-\>float

## Strategy

generate_signal(factors)-\>Signal

## Pattern-Conditioned Context

PatternContextScorer.evaluate(pattern, data, as_of_index)-\>PatternContextEvaluation

PatternContextScorer.score(pattern_result, data)-\>PatternContextEvaluation

PatternContextScorer.score_detected(pattern_results, data)-\>list

ThreePointTrendlineSupport.detect_at(data, anchor_index)-\>PatternResult

ThreePointTrendlineSupport.detect_anchors(data, anchor_indexes)-\>PatternResult

HorizontalSupport.detect_at(data, anchor_index)-\>PatternResult

Horizontal support requires confirmed Swing anchors. Double-bottom anchors
must share a real close/lower-shadow traded-price intersection; ATR is not a
contact-gap tolerance.

HorizontalResistance.detect(data)-\>PatternResult

Horizontal resistance and its fixed-combination lineage share the same exact
open/upper-shadow contact contract. `price_epsilon` is an absolute numerical
tolerance and does not scale with price or ATR.

SupportConfluenceScorer.evaluate(data, event_index, as_of_index)-\>SupportConfluenceEvaluation

support_lineage_features(inverse, horizontal, trendline)-\>dict

SupportLineageScore.calculate(features)-\>FactorResult

The evaluation contains the gated PatternResult, selected FactorResults, and a
0-100 composite FactorResult. See `CONTEXT_FACTORS.md`.

## Fixed Priority Combinations

PriorityCombinationScorer.score(
pattern_result, data, as_of_index, window_start_index)-\>FactorResult

The scorer labels the eight fixed Pattern/EMA99/level-lineage combinations on
`15m`, `1h`, and `4h`. Its EMA99 always belongs to the supplied Pattern
timeframe. Historical scan events expose `priority_fixed_combination`,
`priority_combination_id`, `priority_combination_score`, and
`priority_matched_conditions`. `priority_level_sources` preserves the actual
historical level anchors used by matched conditions for backward-compatible
log/PDF provenance. `priority_level_relations` additionally preserves each
matched condition, relation type, source anchor, target anchor, and shared
level. PDF event charts state symbol, timeframe, Pattern rule, and every
matched fixed-combination condition; they mark relation sources, connect them
to their parent anchors, and draw the causal EMA99 from the same timeframe.
See `PRIORITY_COMBINATIONS.md`.

Support confluence is event anchored: pattern detection may use bars through
the swing-confirmation index, while EMA99 and reclaim features are frozen at
the third-point candle close.

## Retrospective Anchor Outcome Audit

AnchorTradeOutcomeEvaluator.plan(event, bars)-\>AnchorTradePlan | None

AnchorTradeOutcomeEvaluator.evaluate(event, bars)-\>AnchorTradeOutcome | None

write_anchor_trade_report(events, bars_by_timeframe, output_path, source_pdf)
    -\>Path

The audit maps PATTERN_002-008 to their requested second, right-shoulder, or
third anchor and labels the first gross ±1.5% barrier touch. Triangle direction
is frozen at the earliest boundary anchor. Same-candle dual touches resolve
stop-first, unresolved cases remain in the denominator, and FIXED_COMBO
outcomes are summarized separately. Default net-return estimates include
fees and slippage.

This API is deliberately retrospective: it records Pattern confirmation delay
and `causal_at_anchor` rather than emitting a live signal from an anchor that
was not yet confirmed. See `BACKTEST.md`.
