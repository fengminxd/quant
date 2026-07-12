"""Abstract API interfaces from API.md."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from core.models import Bar, FactorResult, FeatureResult, PatternResult, Signal


class Feature(ABC):
    """Feature interface."""

    @abstractmethod
    def compute(self, data: Sequence[Bar]) -> FeatureResult:
        """Compute a feature from historical data only."""


class Factor(ABC):
    """Factor interface."""

    @abstractmethod
    def calculate(self, features: Mapping[str, FeatureResult]) -> FactorResult:
        """Convert features into a 0-100 score."""


class Pattern(ABC):
    """Pattern interface."""

    @abstractmethod
    def detect(self, data: Sequence[Bar]) -> PatternResult:
        """Detect the pattern in historical data."""

    @abstractmethod
    def extract_features(self, data: Sequence[Bar]) -> Mapping[str, FeatureResult]:
        """Extract reusable pattern features."""

    @abstractmethod
    def calculate_score(self, features: Mapping[str, FeatureResult]) -> float:
        """Calculate a 0-100 pattern quality score."""

    @abstractmethod
    def visualize(self, result: PatternResult) -> Mapping[str, object]:
        """Return serializable geometry for downstream visualization."""


class Strategy(ABC):
    """Strategy interface. Production trading is intentionally out of scope."""

    @abstractmethod
    def generate_signal(self, factors: Mapping[str, FactorResult]) -> Signal:
        """Generate a strategy signal from scored factors."""
