# API

## Pattern

detect(data)-\>PatternResult extract_features(data)-\>dict
calculate_score(features)-\>float

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

SupportConfluenceScorer.evaluate(data, event_index, as_of_index)-\>SupportConfluenceEvaluation

support_lineage_features(inverse, horizontal, trendline)-\>dict

SupportLineageScore.calculate(features)-\>FactorResult

The evaluation contains the gated PatternResult, selected FactorResults, and a
0-100 composite FactorResult. See `CONTEXT_FACTORS.md`.

Support confluence is event anchored: pattern detection may use bars through
the swing-confirmation index, while EMA99 and reclaim features are frozen at
the third-point candle close.
