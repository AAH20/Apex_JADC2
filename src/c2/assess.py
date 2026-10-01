"""F2T2EA Assess Phase — Battle Damage Assessment, Engagement Evaluation, Re-attack Recommendation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .f2t2ea import (
    EngagementOutcome,
    EngagementResult,
    HumanDecision,
    HumanGovernance,
    Target,
    ThreatLevel,
)


class DamageLevel(str, Enum):
    """Damage classification levels."""

    DESTROYED = "destroyed"
    HEAVILY_DAMAGED = "heavily_damaged"
    LIGHTLY_DAMAGED = "lightly_damaged"
    UNDAMAGED = "undamaged"


class ReAttackPriority(str, Enum):
    """Re-attack priority levels."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IMMEDIATE = "immediate"


@dataclass
class DamageAssessment:
    """Detailed damage assessment for a target."""

    target_id: str
    damage_level: DamageLevel
    effectiveness: float
    confidence: float
    assessment_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""


@dataclass
class EngagementEvaluation:
    """Evaluation of an engagement."""

    engagement_id: str
    target_id: str
    shooter_id: str
    outcome: EngagementOutcome
    effectiveness: float
    timeliness: float
    accuracy: float
    overall_score: float
    evaluation_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ReAttackRecommendation:
    """Recommendation for re-attack."""

    target_id: str
    should_re_attack: bool
    priority: ReAttackPriority
    reason: str
    recommended_shooter_id: Optional[str] = None
    recommended_weapon: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BattleDamageAssessor:
    """Performs battle damage assessment on targets."""

    def __init__(self, effectiveness_threshold: float = 0.5):
        if not 0.0 <= effectiveness_threshold <= 1.0:
            raise ValueError("effectiveness_threshold must be between 0 and 1")
        self.effectiveness_threshold = effectiveness_threshold
        self._assessments: dict[str, DamageAssessment] = {}

    def assess_damage(
        self,
        target_id: str,
        effectiveness: float,
        confidence: float = 1.0,
        collateral_damage: bool = False,
        notes: str = "",
    ) -> DamageAssessment:
        """Assess damage to a target."""
        if not 0.0 <= effectiveness <= 1.0:
            raise ValueError("effectiveness must be between 0 and 1")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        damage_level = self._classify_damage(effectiveness)
        assessment = DamageAssessment(
            target_id=target_id,
            damage_level=damage_level,
            effectiveness=effectiveness,
            confidence=confidence,
            notes=notes,
        )
        self._assessments[target_id] = assessment
        return assessment

    def _classify_damage(self, effectiveness: float) -> DamageLevel:
        """Classify damage level based on effectiveness."""
        if effectiveness >= 0.9:
            return DamageLevel.DESTROYED
        elif effectiveness >= 0.7:
            return DamageLevel.HEAVILY_DAMAGED
        elif effectiveness >= 0.3:
            return DamageLevel.LIGHTLY_DAMAGED
        else:
            return DamageLevel.UNDAMAGED

    def get_assessment(self, target_id: str) -> Optional[DamageAssessment]:
        """Get the latest assessment for a target."""
        return self._assessments.get(target_id)

    def requires_re_engagement(self, target_id: str) -> bool:
        """Check if a target requires re-engagement."""
        assessment = self._assessments.get(target_id)
        if assessment is None:
            return False
        return assessment.effectiveness < self.effectiveness_threshold

    def get_all_assessments(self) -> dict[str, DamageAssessment]:
        """Return all assessments."""
        return dict(self._assessments)

    def get_damage_summary(self) -> dict[str, int]:
        """Return summary of damage levels."""
        summary = {level.value: 0 for level in DamageLevel}
        for assessment in self._assessments.values():
            summary[assessment.damage_level.value] += 1
        return summary


class EngagementEvaluator:
    """Evaluates engagement performance."""

    def __init__(self):
        self._evaluations: dict[str, EngagementEvaluation] = {}
        self._counter = 0

    def evaluate(
        self,
        engagement: EngagementResult,
        target: Optional[Target] = None,
        expected_duration_seconds: Optional[float] = None,
    ) -> EngagementEvaluation:
        """Evaluate an engagement."""
        self._counter += 1
        engagement_id = f"eval-{self._counter}"

        effectiveness = self._compute_effectiveness(engagement, target)
        timeliness = self._compute_timeliness(engagement, expected_duration_seconds)
        accuracy = self._compute_accuracy(engagement, target)
        overall = (effectiveness + timeliness + accuracy) / 3.0

        evaluation = EngagementEvaluation(
            engagement_id=engagement_id,
            target_id=engagement.target_id,
            shooter_id=engagement.shooter_id,
            outcome=engagement.outcome,
            effectiveness=effectiveness,
            timeliness=timeliness,
            accuracy=accuracy,
            overall_score=overall,
        )
        self._evaluations[engagement_id] = evaluation
        return evaluation

    def _compute_effectiveness(
        self, engagement: EngagementResult, target: Optional[Target]
    ) -> float:
        """Compute effectiveness score."""
        if engagement.outcome == EngagementOutcome.SUCCESS:
            return 1.0
        elif engagement.outcome == EngagementOutcome.PARTIAL:
            return 0.5
        else:
            return 0.0

    def _compute_timeliness(
        self, engagement: EngagementResult, expected_duration: Optional[float]
    ) -> float:
        """Compute timeliness score."""
        if expected_duration is None or expected_duration <= 0:
            return 1.0
        return 1.0

    def _compute_accuracy(
        self, engagement: EngagementResult, target: Optional[Target]
    ) -> float:
        """Compute accuracy score."""
        if engagement.outcome == EngagementOutcome.SUCCESS:
            return 1.0
        elif engagement.outcome == EngagementOutcome.PARTIAL:
            return 0.6
        else:
            return 0.2

    def get_evaluation(self, engagement_id: str) -> Optional[EngagementEvaluation]:
        """Get an evaluation by ID."""
        return self._evaluations.get(engagement_id)

    def get_all_evaluations(self) -> dict[str, EngagementEvaluation]:
        """Return all evaluations."""
        return dict(self._evaluations)

    def average_effectiveness(self) -> float:
        """Return average effectiveness across all evaluations."""
        if not self._evaluations:
            return 0.0
        return sum(e.effectiveness for e in self._evaluations.values()) / len(self._evaluations)

    def success_rate(self) -> float:
        """Return success rate across all evaluations."""
        if not self._evaluations:
            return 0.0
        successes = sum(
            1 for e in self._evaluations.values()
            if e.outcome == EngagementOutcome.SUCCESS
        )
        return successes / len(self._evaluations)


class ReAttackRecommender:
    """Recommends re-attack based on damage assessment and threat level."""

    def __init__(
        self,
        assessor: BattleDamageAssessor,
        evaluator: EngagementEvaluator,
        governance: Optional[HumanGovernance] = None,
    ):
        self.assessor = assessor
        self.evaluator = evaluator
        self.governance = governance
        self._recommendations: dict[str, ReAttackRecommendation] = {}

    def recommend(
        self,
        target_id: str,
        target: Optional[Target] = None,
        available_shooters: Optional[list[str]] = None,
    ) -> ReAttackRecommendation:
        """Generate a re-attack recommendation."""
        assessment = self.assessor.get_assessment(target_id)

        if assessment is None:
            rec = ReAttackRecommendation(
                target_id=target_id,
                should_re_attack=False,
                priority=ReAttackPriority.NONE,
                reason="No damage assessment available",
            )
            self._recommendations[target_id] = rec
            return rec

        if assessment.damage_level == DamageLevel.DESTROYED:
            rec = ReAttackRecommendation(
                target_id=target_id,
                should_re_attack=False,
                priority=ReAttackPriority.NONE,
                reason="Target destroyed",
            )
            self._recommendations[target_id] = rec
            return rec

        priority = self._determine_priority(assessment, target)
        should_re_attack = priority != ReAttackPriority.NONE

        if should_re_attack and self.governance is not None:
            if not self.governance.is_authorized(HumanDecision.ENGAGE, target_id):
                should_re_attack = False
                priority = ReAttackPriority.NONE

        reason = self._generate_reason(assessment, target, priority)

        rec = ReAttackRecommendation(
            target_id=target_id,
            should_re_attack=should_re_attack,
            priority=priority,
            reason=reason,
        )
        self._recommendations[target_id] = rec
        return rec

    def _determine_priority(
        self, assessment: DamageAssessment, target: Optional[Target]
    ) -> ReAttackPriority:
        """Determine re-attack priority."""
        if assessment.damage_level == DamageLevel.HEAVILY_DAMAGED:
            if target and target.threat_level >= ThreatLevel.HIGH:
                return ReAttackPriority.HIGH
            return ReAttackPriority.MEDIUM
        elif assessment.damage_level == DamageLevel.LIGHTLY_DAMAGED:
            if target and target.threat_level >= ThreatLevel.HIGH:
                return ReAttackPriority.MEDIUM
            return ReAttackPriority.LOW
        else:
            if target and target.threat_level >= ThreatLevel.CRITICAL:
                return ReAttackPriority.IMMEDIATE
            elif target and target.threat_level >= ThreatLevel.HIGH:
                return ReAttackPriority.HIGH
            return ReAttackPriority.MEDIUM

    def _generate_reason(
        self, assessment: DamageAssessment, target: Optional[Target], priority: ReAttackPriority
    ) -> str:
        """Generate a human-readable reason."""
        if priority == ReAttackPriority.NONE:
            return "No re-attack needed"
        threat_str = f" (threat: {target.threat_level.name})" if target else ""
        return (
            f"Target {assessment.target_id} is {assessment.damage_level.value} "
            f"with effectiveness {assessment.effectiveness:.2f}{threat_str}"
        )

    def get_recommendation(self, target_id: str) -> Optional[ReAttackRecommendation]:
        """Get a recommendation by target ID."""
        return self._recommendations.get(target_id)

    def get_all_recommendations(self) -> dict[str, ReAttackRecommendation]:
        """Return all recommendations."""
        return dict(self._recommendations)
