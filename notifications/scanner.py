"""Latest-candle scanner isolated from trading and report policy gates."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from core.models import Bar, FactorResult, PatternResult
from factors.priority_combinations import PriorityFixedCombinationScore
from features.priority_combinations import PriorityCombinationFeatureExtractor
from notifications.config import HISTORY_BARS, NOTIFICATION_TIMEFRAMES
from notifications.models import NotificationMatch
from notifications.pattern_adapters import notification_patterns
from patterns.detector import PatternDetector


class NotificationPriorityScorer:
    """Evaluate all fixed combinations, including notification-only COMBO_006."""

    def __init__(
        self,
        extractor: PriorityCombinationFeatureExtractor | None = None,
    ) -> None:
        self.extractor = extractor or PriorityCombinationFeatureExtractor()

    def score(
        self,
        pattern: PatternResult,
        bars: Sequence[Bar],
    ) -> FactorResult | None:
        """Return an active combination without consulting trading policy."""

        feature_set = self.extractor.extract(
            pattern,
            bars,
            as_of_index=len(bars) - 1,
            window_start_index=0,
        )
        if feature_set is None:
            return None
        result = PriorityFixedCombinationScore(feature_set).calculate(
            feature_set.features
        )
        return result if result.metadata.get("active") else None


class NotificationPatternScanner:
    """Detect PATTERN_002-008 on exactly 201 visible closed candles."""

    def __init__(
        self,
        patterns: Iterable[object] | None = None,
        priority_scorer: NotificationPriorityScorer | None = None,
    ) -> None:
        selected = notification_patterns() if patterns is None else patterns
        self.detector = PatternDetector(selected)  # type: ignore[arg-type]
        self.priority_scorer = priority_scorer or NotificationPriorityScorer()

    def scan(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Bar],
    ) -> list[NotificationMatch]:
        """Return structures whose unconfirmed final anchor is candle 201."""

        if timeframe not in NOTIFICATION_TIMEFRAMES:
            raise ValueError(f"notification timeframe must be one of {NOTIFICATION_TIMEFRAMES}")
        if len(bars) != HISTORY_BARS:
            raise ValueError(f"notification scan requires exactly {HISTORY_BARS} bars")
        if any(bar.timeframe not in (None, timeframe) for bar in bars):
            raise ValueError("bar timeframe does not match notification timeframe")
        last_index = len(bars) - 1
        matches: list[NotificationMatch] = []
        for result in self.detector.detect(bars):
            if not result.detected or not _uses_right_edge(result, last_index):
                continue
            combination = self.priority_scorer.score(result, bars)
            matches.append(
                NotificationMatch(
                    symbol=symbol,
                    timeframe=timeframe,
                    detected_timestamp=bars[-1].timestamp,
                    pattern=result,
                    combination=combination,
                )
            )
        return sorted(matches, key=lambda item: item.pattern.pattern_id)


def _uses_right_edge(result: PatternResult, last_index: int) -> bool:
    """Require the latest closed candle to be a selected Pattern anchor."""

    geometry = result.geometry
    names = (
        ("upper_points", "lower_points")
        if result.pattern_id == "PATTERN_002"
        else ("points",)
    )
    return any(
        index == last_index
        for name in names
        for index in _point_indexes(geometry.get(name, ()))
    )


def _point_indexes(raw: object) -> Iterable[int]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return
    for point in raw:
        if (
            isinstance(point, Sequence)
            and not isinstance(point, (str, bytes))
            and point
            and isinstance(point[0], (int, float))
        ):
            yield int(point[0])
