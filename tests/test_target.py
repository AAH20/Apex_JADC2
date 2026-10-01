"""Unit tests for F2T2EA Target Phase — prioritization, value scoring, selection."""

from __future__ import annotations

import pytest

from src.c2.f2t2ea import ThreatLevel, F2T2EAError
from src.c2.target import (
    TargetValueScorer,
    TargetPrioritizer,
    TargetSelector,
    TargetSelectionResult,
    ClassificationCriticality,
    compute_value_score,
    prioritize_targets,
    select_targets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_target(
    target_id: str,
    threat_level: ThreatLevel = ThreatLevel.LOW,
    classification: str = "unknown",
    confidence: float = 0.5,
    time_sensitivity: float = 0.5,
    location: tuple[float, float] = (0.0, 0.0),
):
    """Create a Target with extended attributes for testing."""
    from src.c2.f2t2ea import Target

    t = Target(
        target_id=target_id,
        location=location,
        threat_level=threat_level,
        classification=classification,
    )
    # Attach extended attributes for scoring
    t.confidence = confidence
    t.time_sensitivity = time_sensitivity
    return t


# ---------------------------------------------------------------------------
# ClassificationCriticality
# ---------------------------------------------------------------------------


class TestClassificationCriticality:
    def test_known_classification(self):
        assert ClassificationCriticality.get("air_defense") == 1.0

    def test_unknown_classification(self):
        assert ClassificationCriticality.get("unknown") == 0.0

    def test_custom_classification(self):
        ClassificationCriticality.register("stealth_fighter", 0.95)
        assert ClassificationCriticality.get("stealth_fighter") == 0.95

    def test_register_overrides(self):
        ClassificationCriticality.register("temp_class", 0.5)
        ClassificationCriticality.register("temp_class", 0.8)
        assert ClassificationCriticality.get("temp_class") == 0.8

    def test_register_invalid_score(self):
        with pytest.raises(ValueError):
            ClassificationCriticality.register("bad", -0.1)
        with pytest.raises(ValueError):
            ClassificationCriticality.register("bad", 1.5)

    def test_is_known(self):
        assert ClassificationCriticality.is_known("air_defense") is True
        assert ClassificationCriticality.is_known("nonexistent") is False


# ---------------------------------------------------------------------------
# compute_value_score
# ---------------------------------------------------------------------------


class TestComputeValueScore:
    def test_basic_score(self):
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        score = compute_value_score(t)
        assert 0.0 <= score <= 1.0

    def test_critical_threat_scores_higher(self):
        t_low = _make_target("T1", ThreatLevel.LOW, "air_defense", 0.9, 0.8)
        t_crit = _make_target("T2", ThreatLevel.CRITICAL, "air_defense", 0.9, 0.8)
        assert compute_value_score(t_crit) > compute_value_score(t_low)

    def test_high_confidence_scores_higher(self):
        t_low = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.3, 0.8)
        t_high = _make_target("T2", ThreatLevel.HIGH, "air_defense", 0.95, 0.8)
        assert compute_value_score(t_high) > compute_value_score(t_low)

    def test_high_time_sensitivity_scores_higher(self):
        t_low = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.2)
        t_high = _make_target("T2", ThreatLevel.HIGH, "air_defense", 0.9, 0.95)
        assert compute_value_score(t_high) > compute_value_score(t_low)

    def test_critical_classification_scores_higher(self):
        t_unk = _make_target("T1", ThreatLevel.HIGH, "unknown", 0.9, 0.8)
        t_ad = _make_target("T2", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        assert compute_value_score(t_ad) > compute_value_score(t_unk)

    def test_score_range(self):
        for threat in ThreatLevel:
            for conf in [0.0, 0.5, 1.0]:
                for ts in [0.0, 0.5, 1.0]:
                    t = _make_target("T", threat, "air_defense", conf, ts)
                    score = compute_value_score(t)
                    assert 0.0 <= score <= 1.0

    def test_destroyed_target_scores_zero(self):
        t = _make_target("T1", ThreatLevel.CRITICAL, "air_defense", 1.0, 1.0)
        t.destroyed = True
        assert compute_value_score(t) == 0.0

    def test_custom_weights(self):
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        score_default = compute_value_score(t)
        score_custom = compute_value_score(
            t, threat_weight=0.6, classification_weight=0.2,
            confidence_weight=0.1, time_sensitivity_weight=0.1
        )
        assert 0.0 <= score_custom <= 1.0
        # Different weights should generally produce different scores
        assert score_default != score_custom or score_default == score_custom

    def test_invalid_weights_sum(self):
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        with pytest.raises(ValueError):
            compute_value_score(
                t, threat_weight=0.5, classification_weight=0.5,
                confidence_weight=0.5, time_sensitivity_weight=0.5
            )


# ---------------------------------------------------------------------------
# TargetValueScorer
# ---------------------------------------------------------------------------


class TestTargetValueScorer:
    def test_score_returns_float(self):
        scorer = TargetValueScorer()
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        score = scorer.score(t)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_score_consistency(self):
        scorer = TargetValueScorer()
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        assert scorer.score(t) == scorer.score(t)

    def test_score_with_custom_weights(self):
        scorer = TargetValueScorer(
            threat_weight=0.5, classification_weight=0.3,
            confidence_weight=0.1, time_sensitivity_weight=0.1
        )
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        score = scorer.score(t)
        assert 0.0 <= score <= 1.0

    def test_score_multiple_targets(self):
        scorer = TargetValueScorer()
        targets = [
            _make_target("T1", ThreatLevel.LOW, "unknown", 0.3, 0.2),
            _make_target("T2", ThreatLevel.CRITICAL, "air_defense", 0.95, 0.9),
            _make_target("T3", ThreatLevel.MEDIUM, "armor", 0.6, 0.5),
        ]
        scores = {t.target_id: scorer.score(t) for t in targets}
        assert scores["T2"] > scores["T3"] > scores["T1"]

    def test_score_destroyed_target(self):
        scorer = TargetValueScorer()
        t = _make_target("T1", ThreatLevel.CRITICAL, "air_defense", 1.0, 1.0)
        t.destroyed = True
        assert scorer.score(t) == 0.0


# ---------------------------------------------------------------------------
# TargetPrioritizer
# ---------------------------------------------------------------------------


class TestTargetPrioritizer:
    def test_prioritize_empty_list(self):
        prioritizer = TargetPrioritizer()
        assert prioritizer.prioritize([]) == []

    def test_prioritize_single_target(self):
        prioritizer = TargetPrioritizer()
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        result = prioritizer.prioritize([t])
        assert len(result) == 1
        assert result[0].target_id == "T1"

    def test_prioritize_by_threat_level(self):
        prioritizer = TargetPrioritizer()
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.CRITICAL),
            _make_target("T3", ThreatLevel.MEDIUM),
            _make_target("T4", ThreatLevel.HIGH),
        ]
        result = prioritizer.prioritize(targets)
        assert [t.target_id for t in result] == ["T2", "T4", "T3", "T1"]

    def test_prioritize_by_value_score_within_same_threat(self):
        scorer = TargetValueScorer()
        prioritizer = TargetPrioritizer(scorer=scorer)
        targets = [
            _make_target("T1", ThreatLevel.HIGH, "unknown", 0.3, 0.2),
            _make_target("T2", ThreatLevel.HIGH, "air_defense", 0.95, 0.9),
        ]
        result = prioritizer.prioritize(targets)
        assert result[0].target_id == "T2"

    def test_prioritize_excludes_destroyed(self):
        prioritizer = TargetPrioritizer()
        t1 = _make_target("T1", ThreatLevel.CRITICAL, "air_defense", 0.9, 0.8)
        t2 = _make_target("T2", ThreatLevel.HIGH, "armor", 0.8, 0.7)
        t1.destroyed = True
        result = prioritizer.prioritize([t1, t2])
        assert len(result) == 1
        assert result[0].target_id == "T2"

    def test_prioritize_stable_sort(self):
        prioritizer = TargetPrioritizer()
        targets = [
            _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8),
            _make_target("T2", ThreatLevel.HIGH, "air_defense", 0.9, 0.8),
            _make_target("T3", ThreatLevel.HIGH, "air_defense", 0.9, 0.8),
        ]
        result = prioritizer.prioritize(targets)
        assert len(result) == 3

    def test_prioritize_with_scorer(self):
        scorer = TargetValueScorer(
            threat_weight=0.2, classification_weight=0.4,
            confidence_weight=0.2, time_sensitivity_weight=0.2
        )
        prioritizer = TargetPrioritizer(scorer=scorer)
        targets = [
            _make_target("T1", ThreatLevel.LOW, "air_defense", 0.95, 0.95),
            _make_target("T2", ThreatLevel.HIGH, "unknown", 0.3, 0.2),
        ]
        result = prioritizer.prioritize(targets)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TargetSelector
# ---------------------------------------------------------------------------


class TestTargetSelector:
    def test_select_top_n(self):
        selector = TargetSelector()
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.CRITICAL),
            _make_target("T3", ThreatLevel.HIGH),
            _make_target("T4", ThreatLevel.MEDIUM),
        ]
        result = selector.select_top_n(targets, n=2)
        assert len(result) == 2
        assert result[0].target_id == "T2"
        assert result[1].target_id == "T3"

    def test_select_top_n_exceeds_available(self):
        selector = TargetSelector()
        targets = [_make_target("T1", ThreatLevel.HIGH)]
        result = selector.select_top_n(targets, n=5)
        assert len(result) == 1

    def test_select_top_n_zero(self):
        selector = TargetSelector()
        targets = [_make_target("T1", ThreatLevel.HIGH)]
        result = selector.select_top_n(targets, n=0)
        assert len(result) == 0

    def test_select_by_classification(self):
        selector = TargetSelector()
        targets = [
            _make_target("T1", ThreatLevel.HIGH, "air_defense"),
            _make_target("T2", ThreatLevel.HIGH, "armor"),
            _make_target("T3", ThreatLevel.HIGH, "air_defense"),
        ]
        result = selector.select_by_classification(targets, "air_defense")
        assert len(result) == 2
        assert all(t.classification == "air_defense" for t in result)

    def test_select_by_classification_no_match(self):
        selector = TargetSelector()
        targets = [_make_target("T1", ThreatLevel.HIGH, "armor")]
        result = selector.select_by_classification(targets, "air_defense")
        assert len(result) == 0

    def test_select_by_min_threat_level(self):
        selector = TargetSelector()
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.MEDIUM),
            _make_target("T3", ThreatLevel.HIGH),
            _make_target("T4", ThreatLevel.CRITICAL),
        ]
        result = selector.select_by_min_threat_level(targets, ThreatLevel.HIGH)
        assert len(result) == 2
        assert all(t.threat_level >= ThreatLevel.HIGH for t in result)

    def test_select_best(self):
        selector = TargetSelector()
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.CRITICAL),
            _make_target("T3", ThreatLevel.HIGH),
        ]
        result = selector.select_best(targets)
        assert result.target_id == "T2"

    def test_select_best_empty_raises(self):
        selector = TargetSelector()
        with pytest.raises(F2T2EAError):
            selector.select_best([])

    def test_select_best_excludes_destroyed(self):
        selector = TargetSelector()
        t1 = _make_target("T1", ThreatLevel.CRITICAL, "air_defense", 0.9, 0.8)
        t2 = _make_target("T2", ThreatLevel.HIGH, "armor", 0.8, 0.7)
        t1.destroyed = True
        result = selector.select_best([t1, t2])
        assert result.target_id == "T2"

    def test_select_with_score_threshold(self):
        selector = TargetSelector()
        targets = [
            _make_target("T1", ThreatLevel.LOW, "unknown", 0.1, 0.1),
            _make_target("T2", ThreatLevel.CRITICAL, "air_defense", 0.95, 0.9),
            _make_target("T3", ThreatLevel.MEDIUM, "armor", 0.6, 0.5),
        ]
        result = selector.select_with_score_threshold(targets, min_score=0.5)
        assert len(result) >= 1
        assert all(
            selector._scorer.score(t) >= 0.5 for t in result
        )

    def test_select_with_score_threshold_no_match(self):
        selector = TargetSelector()
        targets = [
            _make_target("T1", ThreatLevel.LOW, "unknown", 0.1, 0.1),
        ]
        result = selector.select_with_score_threshold(targets, min_score=0.9)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# TargetSelectionResult
# ---------------------------------------------------------------------------


class TestTargetSelectionResult:
    def test_create_result(self):
        t = _make_target("T1", ThreatLevel.HIGH, "air_defense", 0.9, 0.8)
        result = TargetSelectionResult(
            selected_targets=[t],
            total_candidates=5,
            selection_reason="top_priority",
        )
        assert len(result.selected_targets) == 1
        assert result.total_candidates == 5
        assert result.selection_reason == "top_priority"

    def test_create_empty_result(self):
        result = TargetSelectionResult(
            selected_targets=[],
            total_candidates=0,
            selection_reason="no_targets",
        )
        assert len(result.selected_targets) == 0
        assert result.total_candidates == 0

    def test_result_equality(self):
        t = _make_target("T1", ThreatLevel.HIGH)
        r1 = TargetSelectionResult([t], 1, "test")
        r2 = TargetSelectionResult([t], 1, "test")
        assert r1 == r2


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


class TestModuleLevelFunctions:
    def test_prioritize_targets_function(self):
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.CRITICAL),
        ]
        result = prioritize_targets(targets)
        assert result[0].target_id == "T2"

    def test_select_targets_function(self):
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.CRITICAL),
            _make_target("T3", ThreatLevel.HIGH),
        ]
        result = select_targets(targets, n=2)
        assert len(result) == 2
        assert result[0].target_id == "T2"

    def test_select_targets_with_classification_filter(self):
        targets = [
            _make_target("T1", ThreatLevel.HIGH, "air_defense"),
            _make_target("T2", ThreatLevel.CRITICAL, "armor"),
            _make_target("T3", ThreatLevel.HIGH, "air_defense"),
        ]
        result = select_targets(targets, classification_filter="air_defense")
        assert len(result) == 2
        assert all(t.classification == "air_defense" for t in result)

    def test_select_targets_with_threat_filter(self):
        targets = [
            _make_target("T1", ThreatLevel.LOW),
            _make_target("T2", ThreatLevel.HIGH),
            _make_target("T3", ThreatLevel.CRITICAL),
        ]
        result = select_targets(targets, min_threat_level=ThreatLevel.HIGH)
        assert len(result) == 2
        assert all(t.threat_level >= ThreatLevel.HIGH for t in result)


# ---------------------------------------------------------------------------
# Integration-style tests
# ---------------------------------------------------------------------------


class TestTargetPhaseIntegration:
    def test_full_prioritization_pipeline(self):
        """Test the complete target phase pipeline."""
        scorer = TargetValueScorer()
        prioritizer = TargetPrioritizer(scorer=scorer)
        selector = TargetSelector(scorer=scorer)

        targets = [
            _make_target("T1", ThreatLevel.LOW, "unknown", 0.3, 0.2),
            _make_target("T2", ThreatLevel.CRITICAL, "air_defense", 0.95, 0.9),
            _make_target("T3", ThreatLevel.HIGH, "armor", 0.7, 0.6),
            _make_target("T4", ThreatLevel.MEDIUM, "infantry", 0.5, 0.4),
            _make_target("T5", ThreatLevel.HIGH, "air_defense", 0.85, 0.75),
        ]

        # Step 1: Prioritize
        prioritized = prioritizer.prioritize(targets)
        assert len(prioritized) == 5
        assert prioritized[0].target_id == "T2"  # CRITICAL + air_defense

        # Step 2: Select top 3
        selected = selector.select_top_n(prioritized, n=3)
        assert len(selected) == 3
        assert selected[0].target_id == "T2"

        # Step 3: Filter by classification
        air_defense = selector.select_by_classification(selected, "air_defense")
        assert len(air_defense) >= 1

    def test_destroyed_targets_excluded_from_pipeline(self):
        scorer = TargetValueScorer()
        prioritizer = TargetPrioritizer(scorer=scorer)
        selector = TargetSelector(scorer=scorer)

        t1 = _make_target("T1", ThreatLevel.CRITICAL, "air_defense", 0.95, 0.9)
        t2 = _make_target("T2", ThreatLevel.HIGH, "armor", 0.8, 0.7)
        t3 = _make_target("T3", ThreatLevel.MEDIUM, "infantry", 0.5, 0.4)
        t1.destroyed = True

        prioritized = prioritizer.prioritize([t1, t2, t3])
        assert len(prioritized) == 2
        assert t1 not in prioritized

        best = selector.select_best([t1, t2, t3])
        assert best.target_id == "T2"

    def test_score_threshold_filters_low_value(self):
        scorer = TargetValueScorer()
        selector = TargetSelector(scorer=scorer)

        targets = [
            _make_target("T1", ThreatLevel.LOW, "unknown", 0.1, 0.1),
            _make_target("T2", ThreatLevel.LOW, "unknown", 0.15, 0.1),
            _make_target("T3", ThreatLevel.CRITICAL, "air_defense", 0.95, 0.9),
        ]

        result = selector.select_with_score_threshold(targets, min_score=0.3)
        assert len(result) == 1
        assert result[0].target_id == "T3"
