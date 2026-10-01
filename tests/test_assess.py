"""Tests for F2T2EA Assess Phase."""

from __future__ import annotations

import pytest

from src.c2.assess import (
    BattleDamageAssessor,
    DamageLevel,
    EngagementEvaluator,
    ReAttackPriority,
    ReAttackRecommender,
)
from src.c2.f2t2ea import (
    EngagementOutcome,
    EngagementResult,
    HumanDecision,
    HumanGovernance,
    Target,
    ThreatLevel,
)


# ---------------------------------------------------------------------------
# BattleDamageAssessor Tests
# ---------------------------------------------------------------------------


class TestBattleDamageAssessor:
    """Tests for BattleDamageAssessor."""

    def test_assess_damage_destroyed(self):
        """Test damage assessment for destroyed target."""
        assessor = BattleDamageAssessor()
        result = assessor.assess_damage("T1", effectiveness=0.95)
        assert result.damage_level == DamageLevel.DESTROYED
        assert result.effectiveness == 0.95

    def test_assess_damage_heavily_damaged(self):
        """Test damage assessment for heavily damaged target."""
        assessor = BattleDamageAssessor()
        result = assessor.assess_damage("T1", effectiveness=0.75)
        assert result.damage_level == DamageLevel.HEAVILY_DAMAGED

    def test_assess_damage_lightly_damaged(self):
        """Test damage assessment for lightly damaged target."""
        assessor = BattleDamageAssessor()
        result = assessor.assess_damage("T1", effectiveness=0.5)
        assert result.damage_level == DamageLevel.LIGHTLY_DAMAGED

    def test_assess_damage_undamaged(self):
        """Test damage assessment for undamaged target."""
        assessor = BattleDamageAssessor()
        result = assessor.assess_damage("T1", effectiveness=0.1)
        assert result.damage_level == DamageLevel.UNDAMAGED

    def test_assess_damage_invalid_effectiveness(self):
        """Test that invalid effectiveness raises ValueError."""
        assessor = BattleDamageAssessor()
        with pytest.raises(ValueError):
            assessor.assess_damage("T1", effectiveness=1.5)
        with pytest.raises(ValueError):
            assessor.assess_damage("T1", effectiveness=-0.1)

    def test_assess_damage_invalid_confidence(self):
        """Test that invalid confidence raises ValueError."""
        assessor = BattleDamageAssessor()
        with pytest.raises(ValueError):
            assessor.assess_damage("T1", effectiveness=0.5, confidence=1.5)

    def test_requires_re_engagement_true(self):
        """Test re-engagement required for low effectiveness."""
        assessor = BattleDamageAssessor(effectiveness_threshold=0.5)
        assessor.assess_damage("T1", effectiveness=0.3)
        assert assessor.requires_re_engagement("T1") is True

    def test_requires_re_engagement_false(self):
        """Test no re-engagement for high effectiveness."""
        assessor = BattleDamageAssessor(effectiveness_threshold=0.5)
        assessor.assess_damage("T1", effectiveness=0.8)
        assert assessor.requires_re_engagement("T1") is False

    def test_requires_re_engagement_no_assessment(self):
        """Test re-engagement returns False when no assessment exists."""
        assessor = BattleDamageAssessor()
        assert assessor.requires_re_engagement("T1") is False

    def test_get_assessment(self):
        """Test retrieving an assessment."""
        assessor = BattleDamageAssessor()
        assessor.assess_damage("T1", effectiveness=0.6)
        result = assessor.get_assessment("T1")
        assert result is not None
        assert result.target_id == "T1"

    def test_get_assessment_missing(self):
        """Test retrieving a non-existent assessment returns None."""
        assessor = BattleDamageAssessor()
        assert assessor.get_assessment("T1") is None

    def test_get_damage_summary(self):
        """Test damage summary counts."""
        assessor = BattleDamageAssessor()
        assessor.assess_damage("T1", effectiveness=0.95)
        assessor.assess_damage("T2", effectiveness=0.75)
        assessor.assess_damage("T3", effectiveness=0.5)
        assessor.assess_damage("T4", effectiveness=0.1)
        summary = assessor.get_damage_summary()
        assert summary["destroyed"] == 1
        assert summary["heavily_damaged"] == 1
        assert summary["lightly_damaged"] == 1
        assert summary["undamaged"] == 1

    def test_custom_threshold(self):
        """Test custom effectiveness threshold."""
        assessor = BattleDamageAssessor(effectiveness_threshold=0.8)
        assessor.assess_damage("T1", effectiveness=0.7)
        assert assessor.requires_re_engagement("T1") is True

    def test_invalid_threshold(self):
        """Test that invalid threshold raises ValueError."""
        with pytest.raises(ValueError):
            BattleDamageAssessor(effectiveness_threshold=1.5)


# ---------------------------------------------------------------------------
# EngagementEvaluator Tests
# ---------------------------------------------------------------------------


class TestEngagementEvaluator:
    """Tests for EngagementEvaluator."""

    def test_evaluate_success(self):
        """Test evaluation of successful engagement."""
        evaluator = EngagementEvaluator()
        engagement = EngagementResult(
            target_id="T1",
            shooter_id="S1",
            outcome=EngagementOutcome.SUCCESS,
        )
        result = evaluator.evaluate(engagement)
        assert result.effectiveness == 1.0
        assert result.overall_score > 0.0

    def test_evaluate_failure(self):
        """Test evaluation of failed engagement."""
        evaluator = EngagementEvaluator()
        engagement = EngagementResult(
            target_id="T1",
            shooter_id="S1",
            outcome=EngagementOutcome.FAILURE,
        )
        result = evaluator.evaluate(engagement)
        assert result.effectiveness == 0.0

    def test_evaluate_partial(self):
        """Test evaluation of partial engagement."""
        evaluator = EngagementEvaluator()
        engagement = EngagementResult(
            target_id="T1",
            shooter_id="S1",
            outcome=EngagementOutcome.PARTIAL,
        )
        result = evaluator.evaluate(engagement)
        assert result.effectiveness == 0.5

    def test_average_effectiveness(self):
        """Test average effectiveness calculation."""
        evaluator = EngagementEvaluator()
        evaluator.evaluate(
            EngagementResult("T1", "S1", EngagementOutcome.SUCCESS)
        )
        evaluator.evaluate(
            EngagementResult("T2", "S1", EngagementOutcome.FAILURE)
        )
        assert evaluator.average_effectiveness() == 0.5

    def test_success_rate(self):
        """Test success rate calculation."""
        evaluator = EngagementEvaluator()
        evaluator.evaluate(
            EngagementResult("T1", "S1", EngagementOutcome.SUCCESS)
        )
        evaluator.evaluate(
            EngagementResult("T2", "S1", EngagementOutcome.SUCCESS)
        )
        evaluator.evaluate(
            EngagementResult("T3", "S1", EngagementOutcome.FAILURE)
        )
        assert evaluator.success_rate() == pytest.approx(2 / 3)

    def test_empty_evaluations(self):
        """Test metrics with no evaluations."""
        evaluator = EngagementEvaluator()
        assert evaluator.average_effectiveness() == 0.0
        assert evaluator.success_rate() == 0.0

    def test_get_evaluation(self):
        """Test retrieving an evaluation."""
        evaluator = EngagementEvaluator()
        evaluator.evaluate(EngagementResult("T1", "S1", EngagementOutcome.SUCCESS))
        result = evaluator.get_evaluation("eval-1")
        assert result is not None
        assert result.target_id == "T1"


# ---------------------------------------------------------------------------
# ReAttackRecommender Tests
# ---------------------------------------------------------------------------


class TestReAttackRecommender:
    """Tests for ReAttackRecommender."""

    def test_recommend_no_assessment(self):
        """Test recommendation when no assessment exists."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        rec = recommender.recommend("T1")
        assert rec.should_re_attack is False
        assert rec.priority == ReAttackPriority.NONE

    def test_recommend_destroyed_target(self):
        """Test no re-attack for destroyed target."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        assessor.assess_damage("T1", effectiveness=0.95)
        rec = recommender.recommend("T1")
        assert rec.should_re_attack is False
        assert rec.priority == ReAttackPriority.NONE

    def test_recommend_heavily_damaged_high_threat(self):
        """Test high priority for heavily damaged high-threat target."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        assessor.assess_damage("T1", effectiveness=0.75)
        target = Target("T1", (0.0, 0.0), ThreatLevel.HIGH)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True
        assert rec.priority == ReAttackPriority.HIGH

    def test_recommend_heavily_damaged_low_threat(self):
        """Test medium priority for heavily damaged low-threat target."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        assessor.assess_damage("T1", effectiveness=0.75)
        target = Target("T1", (0.0, 0.0), ThreatLevel.LOW)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True
        assert rec.priority == ReAttackPriority.MEDIUM

    def test_recommend_lightly_damaged_critical_threat(self):
        """Test immediate priority for undamaged critical target."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        assessor.assess_damage("T1", effectiveness=0.1)
        target = Target("T1", (0.0, 0.0), ThreatLevel.CRITICAL)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True
        assert rec.priority == ReAttackPriority.IMMEDIATE

    def test_recommend_undamaged_high_threat(self):
        """Test high priority for undamaged high-threat target."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        assessor.assess_damage("T1", effectiveness=0.0)
        target = Target("T1", (0.0, 0.0), ThreatLevel.HIGH)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True
        assert rec.priority == ReAttackPriority.HIGH

    def test_recommend_undamaged_low_threat(self):
        """Test medium priority for undamaged low-threat target."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        assessor.assess_damage("T1", effectiveness=0.0)
        target = Target("T1", (0.0, 0.0), ThreatLevel.LOW)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True
        assert rec.priority == ReAttackPriority.MEDIUM

    def test_recommend_with_governance_authorized(self):
        """Test re-attack allowed when governance authorizes."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        governance = HumanGovernance()
        governance.authorize(HumanDecision.ENGAGE, "commander", "T1")
        recommender = ReAttackRecommender(assessor, evaluator, governance)
        assessor.assess_damage("T1", effectiveness=0.3)
        target = Target("T1", (0.0, 0.0), ThreatLevel.HIGH)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True

    def test_recommend_with_governance_unauthorized(self):
        """Test re-attack blocked when governance does not authorize."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        governance = HumanGovernance()
        recommender = ReAttackRecommender(assessor, evaluator, governance)
        assessor.assess_damage("T1", effectiveness=0.3)
        target = Target("T1", (0.0, 0.0), ThreatLevel.HIGH)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is False
        assert rec.priority == ReAttackPriority.NONE

    def test_get_recommendation(self):
        """Test retrieving a recommendation."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        recommender.recommend("T1")
        rec = recommender.get_recommendation("T1")
        assert rec is not None
        assert rec.target_id == "T1"

    def test_get_all_recommendations(self):
        """Test retrieving all recommendations."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)
        recommender.recommend("T1")
        recommender.recommend("T2")
        all_recs = recommender.get_all_recommendations()
        assert len(all_recs) == 2
        assert "T1" in all_recs
        assert "T2" in all_recs


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestAssessPhaseIntegration:
    """Integration tests for the full assess phase."""

    def test_full_assess_workflow(self):
        """Test complete assess workflow from damage to recommendation."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)

        # Assess damage
        assessment = assessor.assess_damage("T1", effectiveness=0.4)
        assert assessment.damage_level == DamageLevel.LIGHTLY_DAMAGED

        # Evaluate engagement
        engagement = EngagementResult("T1", "S1", EngagementOutcome.PARTIAL)
        evaluation = evaluator.evaluate(engagement)
        assert evaluation.effectiveness == 0.5

        # Get recommendation
        target = Target("T1", (0.0, 0.0), ThreatLevel.HIGH)
        rec = recommender.recommend("T1", target=target)
        assert rec.should_re_attack is True
        assert rec.priority == ReAttackPriority.MEDIUM

    def test_multiple_targets_assessment(self):
        """Test assessing multiple targets."""
        assessor = BattleDamageAssessor()
        evaluator = EngagementEvaluator()
        recommender = ReAttackRecommender(assessor, evaluator)

        targets = [
            ("T1", 0.95, ThreatLevel.LOW),
            ("T2", 0.75, ThreatLevel.HIGH),
            ("T3", 0.3, ThreatLevel.CRITICAL),
        ]

        for tid, eff, threat in targets:
            assessor.assess_damage(tid, effectiveness=eff)
            target = Target(tid, (0.0, 0.0), threat)
            recommender.recommend(tid, target=target)

        all_recs = recommender.get_all_recommendations()
        assert len(all_recs) == 3
        assert all_recs["T1"].should_re_attack is False
        assert all_recs["T2"].should_re_attack is True
        assert all_recs["T3"].should_re_attack is True
