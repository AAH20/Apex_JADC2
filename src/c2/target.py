"""F2T2EA Target Phase — prioritization, value scoring, and selection.

This module implements the Target phase of the F2T2EA kill chain:
- Target value scoring based on threat level, classification criticality,
  confidence, and time sensitivity.
- Target prioritization (sorting by composite value score).
- Target selection (top-N, by classification, by threat level, by score threshold).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.c2.f2t2ea import Target, ThreatLevel, F2T2EAError


# ---------------------------------------------------------------------------
# Classification Criticality Registry
# ---------------------------------------------------------------------------


class ClassificationCriticality:
    """Registry mapping classification strings to criticality scores [0, 1]."""

    _registry: dict[str, float] = {
        "air_defense": 1.0,
        "ballistic_missile": 0.95,
        "radar": 0.9,
        "armor": 0.7,
        "artillery": 0.65,
        "infantry": 0.4,
        "vehicle": 0.5,
        "unknown": 0.0,
    }

    @classmethod
    def get(cls, classification: str) -> float:
        """Return the criticality score for a classification."""
        return cls._registry.get(classification, 0.0)

    @classmethod
    def register(cls, classification: str, score: float) -> None:
        """Register or update a classification criticality score."""
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"Criticality score must be in [0, 1], got {score}")
        cls._registry[classification] = score

    @classmethod
    def is_known(cls, classification: str) -> bool:
        """Check if a classification is registered."""
        return classification in cls._registry


# ---------------------------------------------------------------------------
# Value Score Computation
# ---------------------------------------------------------------------------

# Default weights for the composite value score
DEFAULT_THREAT_WEIGHT = 0.35
DEFAULT_CLASSIFICATION_WEIGHT = 0.25
DEFAULT_CONFIDENCE_WEIGHT = 0.20
DEFAULT_TIME_SENSITIVITY_WEIGHT = 0.20


def compute_value_score(
    target: Target,
    threat_weight: float = DEFAULT_THREAT_WEIGHT,
    classification_weight: float = DEFAULT_CLASSIFICATION_WEIGHT,
    confidence_weight: float = DEFAULT_CONFIDENCE_WEIGHT,
    time_sensitivity_weight: float = DEFAULT_TIME_SENSITIVITY_WEIGHT,
) -> float:
    """Compute a composite value score for a target.

    The score is a weighted combination of:
    - Threat level (normalized to [0, 1])
    - Classification criticality
    - Confidence (sensor/track confidence)
    - Time sensitivity (how time-critical the target is)

    Returns a float in [0, 1]. Destroyed targets always score 0.
    """
    if target.destroyed:
        return 0.0

    total_weight = threat_weight + classification_weight + confidence_weight + time_sensitivity_weight
    if total_weight <= 0:
        raise ValueError("Total weight must be positive")
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError(f"Weights must sum to 1.0, got {total_weight}")

    tw = threat_weight
    cw = classification_weight
    cfw = confidence_weight
    tsw = time_sensitivity_weight

    # Threat level normalized to [0, 1]
    threat_score = target.threat_level.value / ThreatLevel.CRITICAL.value

    # Classification criticality
    class_score = ClassificationCriticality.get(target.classification)

    # Confidence (default 0.5 if not set)
    confidence = getattr(target, "confidence", 0.5)

    # Time sensitivity (default 0.5 if not set)
    time_sens = getattr(target, "time_sensitivity", 0.5)

    score = (
        tw * threat_score
        + cw * class_score
        + cfw * confidence
        + tsw * time_sens
    )

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Target Value Scorer
# ---------------------------------------------------------------------------


class TargetValueScorer:
    """Scores targets using a weighted composite value function."""

    def __init__(
        self,
        threat_weight: float = DEFAULT_THREAT_WEIGHT,
        classification_weight: float = DEFAULT_CLASSIFICATION_WEIGHT,
        confidence_weight: float = DEFAULT_CONFIDENCE_WEIGHT,
        time_sensitivity_weight: float = DEFAULT_TIME_SENSITIVITY_WEIGHT,
    ):
        self.threat_weight = threat_weight
        self.classification_weight = classification_weight
        self.confidence_weight = confidence_weight
        self.time_sensitivity_weight = time_sensitivity_weight

    def score(self, target: Target) -> float:
        """Return the value score for a target."""
        return compute_value_score(
            target,
            threat_weight=self.threat_weight,
            classification_weight=self.classification_weight,
            confidence_weight=self.confidence_weight,
            time_sensitivity_weight=self.time_sensitivity_weight,
        )


# ---------------------------------------------------------------------------
# Target Prioritizer
# ---------------------------------------------------------------------------


class TargetPrioritizer:
    """Prioritizes targets by composite value score (descending)."""

    def __init__(self, scorer: Optional[TargetValueScorer] = None):
        self._scorer = scorer or TargetValueScorer()

    def prioritize(self, targets: list[Target]) -> list[Target]:
        """Return targets sorted by value score (highest first).

        Destroyed targets are excluded.
        """
        active = [t for t in targets if not t.destroyed]
        return sorted(active, key=self._scorer.score, reverse=True)


# ---------------------------------------------------------------------------
# Target Selector
# ---------------------------------------------------------------------------


@dataclass
class TargetSelectionResult:
    """Result of a target selection operation."""

    selected_targets: list[Target] = field(default_factory=list)
    total_candidates: int = 0
    selection_reason: str = ""


class TargetSelector:
    """Selects targets based on various criteria."""

    def __init__(self, scorer: Optional[TargetValueScorer] = None):
        self._scorer = scorer or TargetValueScorer()

    def select_top_n(self, targets: list[Target], n: int) -> list[Target]:
        """Return the top N targets by value score."""
        if n <= 0:
            return []
        prioritized = self._prioritizer().prioritize(targets)
        return prioritized[:n]

    def select_by_classification(self, targets: list[Target], classification: str) -> list[Target]:
        """Return targets matching the given classification, sorted by score."""
        matching = [t for t in targets if t.classification == classification and not t.destroyed]
        return sorted(matching, key=self._scorer.score, reverse=True)

    def select_by_min_threat_level(self, targets: list[Target], min_level: ThreatLevel) -> list[Target]:
        """Return targets at or above the given threat level, sorted by score."""
        matching = [t for t in targets if t.threat_level >= min_level and not t.destroyed]
        return sorted(matching, key=self._scorer.score, reverse=True)

    def select_best(self, targets: list[Target]) -> Target:
        """Return the single highest-value target."""
        prioritized = self._prioritizer().prioritize(targets)
        if not prioritized:
            raise F2T2EAError("No targets available for selection")
        return prioritized[0]

    def select_with_score_threshold(self, targets: list[Target], min_score: float) -> list[Target]:
        """Return targets with value score >= min_score, sorted by score."""
        active = [t for t in targets if not t.destroyed]
        scored = [(t, self._scorer.score(t)) for t in active]
        filtered = [t for t, s in scored if s >= min_score]
        return sorted(filtered, key=self._scorer.score, reverse=True)

    def _prioritizer(self) -> TargetPrioritizer:
        return TargetPrioritizer(scorer=self._scorer)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def prioritize_targets(
    targets: list[Target],
    scorer: Optional[TargetValueScorer] = None,
) -> list[Target]:
    """Convenience function to prioritize targets."""
    prioritizer = TargetPrioritizer(scorer=scorer)
    return prioritizer.prioritize(targets)


def select_targets(
    targets: list[Target],
    n: Optional[int] = None,
    classification_filter: Optional[str] = None,
    min_threat_level: Optional[ThreatLevel] = None,
    min_score: Optional[float] = None,
    scorer: Optional[TargetValueScorer] = None,
) -> list[Target]:
    """Convenience function to select targets with optional filters.

    Filters are applied in order: classification, threat level, score threshold.
    If n is specified, returns at most n targets.
    """
    selector = TargetSelector(scorer=scorer)
    result = [t for t in targets if not t.destroyed]

    if classification_filter is not None:
        result = [t for t in result if t.classification == classification_filter]

    if min_threat_level is not None:
        result = [t for t in result if t.threat_level >= min_threat_level]

    if min_score is not None:
        result = selector.select_with_score_threshold(result, min_score)
    else:
        result = sorted(result, key=selector._scorer.score, reverse=True)

    if n is not None:
        result = result[:n]

    return result
