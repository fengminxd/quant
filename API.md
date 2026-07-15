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

The evaluation contains the gated PatternResult, selected FactorResults, and a
0-100 composite FactorResult. See `CONTEXT_FACTORS.md`.
