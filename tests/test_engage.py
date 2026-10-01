"""Tests for F2T2EA Engage Phase — WTA, Authorization, Deconfliction."""
import pytest
from datetime import datetime, timezone, timedelta

from c2.engage import (
    WeaponType,
    WeaponTargetAssignment,
    EngagementAuthorization,
    DeconflictionRule,
    DeconflictionEngine,
    EngagePhaseError,
    WeaponTargetAssigner,
    EngagementAuthorizer,
    EngagePhase,
    AssignmentResult,
    AuthorizationResult,
    DeconflictionResult,
)


# ---------------------------------------------------------------------------
# WeaponTargetAssignment Tests
# ---------------------------------------------------------------------------

class TestWeaponTargetAssignment:
    """Tests for weapon-target assignment data class."""

    def test_create_assignment(self):
        wta = WeaponTargetAssignment(
            weapon_id="W1",
            target_id="T1",
            shooter_id="S1",
            weapon_type=WeaponType.MISSILE,
            priority=1,
        )
        assert wta.weapon_id == "W1"
        assert wta.target_id == "T1"
        assert wta.shooter_id == "S1"
        assert wta.weapon_type == WeaponType.MISSILE
        assert wta.priority == 1
        assert wta.assigned_at is not None

    def test_assignment_default_priority(self):
        wta = WeaponTargetAssignment(
            weapon_id="W2",
            target_id="T2",
            shooter_id="S2",
            weapon_type=WeaponType.GUN,
        )
        assert wta.priority == 0

    def test_assignment_equality(self):
        wta1 = WeaponTargetAssignment(
            weapon_id="W1", target_id="T1", shooter_id="S1",
            weapon_type=WeaponType.MISSILE, priority=1,
        )
        wta2 = WeaponTargetAssignment(
            weapon_id="W1", target_id="T1", shooter_id="S1",
            weapon_type=WeaponType.MISSILE, priority=1,
        )
        assert wta1 == wta2

    def test_assignment_inequality_different_weapon(self):
        wta1 = WeaponTargetAssignment(
            weapon_id="W1", target_id="T1", shooter_id="S1",
            weapon_type=WeaponType.MISSILE,
        )
        wta2 = WeaponTargetAssignment(
            weapon_id="W2", target_id="T1", shooter_id="S1",
            weapon_type=WeaponType.MISSILE,
        )
        assert wta1 != wta2


class TestWeaponType:
    """Tests for WeaponType enum."""

    def test_weapon_type_values(self):
        assert WeaponType.MISSILE.value == "missile"
        assert WeaponType.GUN.value == "gun"
        assert WeaponType.LASER.value == "laser"
        assert WeaponType.ELECTRONIC_WARFARE.value == "electronic_warfare"

    def test_weapon_type_count(self):
        assert len(WeaponType) == 4


# ---------------------------------------------------------------------------
# WeaponTargetAssigner Tests
# ---------------------------------------------------------------------------

class TestWeaponTargetAssigner:
    """Tests for weapon-target assignment algorithm."""

    def test_register_weapon(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, {"cap1"}, max_range=100.0)
        assert "W1" in assigner.weapons

    def test_register_duplicate_weapon_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, {"cap1"})
        with pytest.raises(EngagePhaseError):
            assigner.register_weapon("W1", WeaponType.GUN, {"cap2"})

    def test_register_shooter(self):
        assigner = WeaponTargetAssigner()
        assigner.register_shooter("S1", {"missile", "gun"}, max_weapons=2)
        assert "S1" in assigner.shooters

    def test_register_duplicate_shooter_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_shooter("S1", {"missile"})
        with pytest.raises(EngagePhaseError):
            assigner.register_shooter("S1", {"gun"})

    def test_assign_weapon_to_target(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, {"anti_air"})
        assigner.register_shooter("S1", {"missile", "anti_air"})
        assigner.register_target("T1")
        result = assigner.assign("T1", "W1", "S1")
        assert result.success
        assert result.assignment is not None
        assert result.assignment.target_id == "T1"
        assert result.assignment.weapon_id == "W1"

    def test_assign_unknown_target_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        with pytest.raises(EngagePhaseError):
            assigner.assign("UNKNOWN", "W1", "S1")

    def test_assign_unknown_weapon_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_shooter("S1", {"missile"})
        assigner.register_target("T1")
        with pytest.raises(EngagePhaseError):
            assigner.assign("T1", "UNKNOWN", "S1")

    def test_assign_unknown_shooter_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_target("T1")
        with pytest.raises(EngagePhaseError):
            assigner.assign("T1", "W1", "UNKNOWN")

    def test_assign_weapon_already_assigned_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        assigner.register_target("T1")
        assigner.assign("T1", "W1", "S1")
        assigner.register_target("T2")
        with pytest.raises(EngagePhaseError):
            assigner.assign("T2", "W1", "S1")

    def test_assign_shooter_at_capacity_raises(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_weapon("W2", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"}, max_weapons=1)
        assigner.register_target("T1")
        assigner.assign("T1", "W1", "S1")
        assigner.register_target("T2")
        with pytest.raises(EngagePhaseError):
            assigner.assign("T2", "W2", "S1")

    def test_assign_weapon_capability_mismatch(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, {"anti_air"})
        assigner.register_shooter("S1", {"gun"})
        assigner.register_target("T1")
        result = assigner.assign("T1", "W1", "S1")
        assert not result.success
        assert result.reason is not None

    def test_auto_assign_single_weapon_single_target(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        result = assigner.auto_assign(["T1"])
        assert len(result.assignments) == 1
        assert result.assignments[0].target_id == "T1"

    def test_auto_assign_multiple_targets_prioritized(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_weapon("W2", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"}, max_weapons=2)
        result = assigner.auto_assign(["T1", "T2"])
        assert len(result.assignments) == 2

    def test_auto_assign_no_weapons_available(self):
        assigner = WeaponTargetAssigner()
        assigner.register_shooter("S1", {"missile"})
        result = assigner.auto_assign(["T1"])
        assert len(result.assignments) == 0
        assert result.unassigned_targets == ["T1"]

    def test_auto_assign_respects_threat_priority(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"}, max_weapons=1)
        # T2 has higher threat, should get the weapon
        result = assigner.auto_assign(["T1", "T2"], threat_levels={"T1": 1, "T2": 3})
        assert len(result.assignments) == 1
        assert result.assignments[0].target_id == "T2"

    def test_auto_assign_respects_range(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set(), max_range=50.0)
        assigner.register_shooter("S1", {"missile"})
        result = assigner.auto_assign(["T1"], target_ranges={"T1": 100.0})
        assert len(result.assignments) == 0

    def test_unassign_weapon(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        assigner.register_target("T1")
        assigner.assign("T1", "W1", "S1")
        assigner.unassign("W1")
        assert "W1" not in assigner.active_assignments

    def test_unassign_unknown_weapon_raises(self):
        assigner = WeaponTargetAssigner()
        with pytest.raises(EngagePhaseError):
            assigner.unassign("UNKNOWN")

    def test_get_assignments_for_target(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        assigner.register_target("T1")
        assigner.assign("T1", "W1", "S1")
        assignments = assigner.get_assignments_for_target("T1")
        assert len(assignments) == 1
        assert assignments[0].weapon_id == "W1"

    def test_get_assignments_for_shooter(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        assigner.register_target("T1")
        assigner.assign("T1", "W1", "S1")
        assignments = assigner.get_assignments_for_shooter("S1")
        assert len(assignments) == 1

    def test_clear_all_assignments(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"})
        assigner.register_target("T1")
        assigner.assign("T1", "W1", "S1")
        assigner.clear_all()
        assert len(assigner.active_assignments) == 0


# ---------------------------------------------------------------------------
# EngagementAuthorization Tests
# ---------------------------------------------------------------------------

class TestEngagementAuthorization:
    """Tests for engagement authorization data class."""

    def test_create_authorization(self):
        auth = EngagementAuthorization(
            target_id="T1",
            authorized=True,
            authorizer_id="A1",
            authorization_type="explicit",
        )
        assert auth.target_id == "T1"
        assert auth.authorized is True
        assert auth.authorizer_id == "A1"
        assert auth.authorization_type == "explicit"
        assert auth.expires_at is None

    def test_authorization_with_expiry(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        auth = EngagementAuthorization(
            target_id="T1",
            authorized=True,
            authorizer_id="A1",
            authorization_type="explicit",
            expires_at=expires,
        )
        assert auth.expires_at == expires

    def test_authorization_is_expired(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        auth = EngagementAuthorization(
            target_id="T1",
            authorized=True,
            authorizer_id="A1",
            authorization_type="explicit",
            expires_at=past,
        )
        assert auth.is_expired()

    def test_authorization_not_expired(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        auth = EngagementAuthorization(
            target_id="T1",
            authorized=True,
            authorizer_id="A1",
            authorization_type="explicit",
            expires_at=future,
        )
        assert not auth.is_expired()

    def test_authorization_no_expiry_never_expires(self):
        auth = EngagementAuthorization(
            target_id="T1",
            authorized=True,
            authorizer_id="A1",
            authorization_type="explicit",
        )
        assert not auth.is_expired()


class TestEngagementAuthorizer:
    """Tests for engagement authorization logic."""

    def test_authorize_engagement(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit")
        assert authorizer.is_authorized("T1")

    def test_authorize_with_expiry(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit", ttl_seconds=3600)
        assert authorizer.is_authorized("T1")

    def test_authorization_expires(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit", ttl_seconds=-1)
        assert not authorizer.is_authorized("T1")

    def test_revoke_authorization(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit")
        authorizer.revoke("T1", "A1")
        assert not authorizer.is_authorized("T1")

    def test_revoke_unknown_target_raises(self):
        authorizer = EngagementAuthorizer()
        with pytest.raises(EngagePhaseError):
            authorizer.revoke("UNKNOWN", "A1")

    def test_check_authorization_returns_result(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit")
        result = authorizer.check_authorization("T1")
        assert result.authorized is True
        assert result.target_id == "T1"

    def test_check_authorization_denied(self):
        authorizer = EngagementAuthorizer()
        result = authorizer.check_authorization("T1")
        assert result.authorized is False

    def test_dual_authorization_required_for_critical(self):
        authorizer = EngagementAuthorizer(require_dual_for_critical=True)
        authorizer.authorize("T1", "A1", "explicit")
        # Only one authorization, should be denied for critical
        result = authorizer.check_authorization("T1", threat_level=3)
        assert result.authorized is False

    def test_dual_authorization_satisfied(self):
        authorizer = EngagementAuthorizer(require_dual_for_critical=True)
        authorizer.authorize("T1", "A1", "explicit")
        authorizer.authorize("T1", "A2", "explicit")
        result = authorizer.check_authorization("T1", threat_level=3)
        assert result.authorized is True

    def test_standoff_authorization_type(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "standoff")
        result = authorizer.check_authorization("T1")
        assert result.authorized is True
        assert result.authorization_type == "standoff"

    def test_get_authorization_info(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit")
        info = authorizer.get_authorization_info("T1")
        assert info is not None
        assert info.target_id == "T1"

    def test_get_authorization_info_none(self):
        authorizer = EngagementAuthorizer()
        info = authorizer.get_authorization_info("T1")
        assert info is None

    def test_clear_authorizations(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "A1", "explicit")
        authorizer.authorize("T2", "A1", "explicit")
        authorizer.clear()
        assert not authorizer.is_authorized("T1")
        assert not authorizer.is_authorized("T2")


# ---------------------------------------------------------------------------
# Deconfliction Tests
# ---------------------------------------------------------------------------

class TestDeconflictionRule:
    """Tests for deconfliction rule data class."""

    def test_create_rule(self):
        rule = DeconflictionRule(
            rule_id="R1",
            rule_type="temporal",
            parameters={"min_interval_seconds": 30},
        )
        assert rule.rule_id == "R1"
        assert rule.rule_type == "temporal"
        assert rule.parameters["min_interval_seconds"] == 30

    def test_rule_default_parameters(self):
        rule = DeconflictionRule(rule_id="R2", rule_type="spatial")
        assert rule.parameters == {}


class TestDeconflictionEngine:
    """Tests for deconfliction engine."""

    def test_add_rule(self):
        engine = DeconflictionEngine()
        rule = DeconflictionRule(rule_id="R1", rule_type="temporal")
        engine.add_rule(rule)
        assert "R1" in engine.rules

    def test_remove_rule(self):
        engine = DeconflictionEngine()
        rule = DeconflictionRule(rule_id="R1", rule_type="temporal")
        engine.add_rule(rule)
        engine.remove_rule("R1")
        assert "R1" not in engine.rules

    def test_remove_unknown_rule_raises(self):
        engine = DeconflictionEngine()
        with pytest.raises(EngagePhaseError):
            engine.remove_rule("UNKNOWN")

    def test_check_temporal_deconfliction_pass(self):
        engine = DeconflictionEngine()
        engine.add_rule(DeconflictionRule(
            rule_id="R1", rule_type="temporal",
            parameters={"min_interval_seconds": 30},
        ))
        result = engine.check_deconfliction("T1", "S1", "W1")
        assert result.is_clear is True

    def test_check_temporal_deconfliction_fail(self):
        engine = DeconflictionEngine()
        engine.add_rule(DeconflictionRule(
            rule_id="R1", rule_type="temporal",
            parameters={"min_interval_seconds": 30},
        ))
        # First engagement
        engine.record_engagement("T1", "S1", "W1")
        # Immediate second engagement should fail
        result = engine.check_deconfliction("T1", "S1", "W1")
        assert result.is_clear is False
        assert result.blocking_rule == "R1"

    def test_check_spatial_deconfliction_pass(self):
        engine = DeconflictionEngine()
        engine.add_rule(DeconflictionRule(
            rule_id="R2", rule_type="spatial",
            parameters={"min_distance_meters": 1000},
        ))
        result = engine.check_deconfliction("T1", "S1", "W1")
        assert result.is_clear is True

    def test_check_spatial_deconfliction_fail(self):
        engine = DeconflictionEngine()
        engine.add_rule(DeconflictionRule(
            rule_id="R2", rule_type="spatial",
            parameters={"min_distance_meters": 1000},
        ))
        engine.record_engagement("T1", "S1", "W1", location=(0.0, 0.0))
        # Same location should fail
        result = engine.check_deconfliction("T1", "S1", "W1", location=(0.0, 0.0))
        assert result.is_clear is False

    def test_record_engagement(self):
        engine = DeconflictionEngine()
        engine.record_engagement("T1", "S1", "W1")
        assert len(engine.engagement_history) == 1

    def test_clear_history(self):
        engine = DeconflictionEngine()
        engine.record_engagement("T1", "S1", "W1")
        engine.clear_history()
        assert len(engine.engagement_history) == 0

    def test_multiple_rules_all_must_pass(self):
        engine = DeconflictionEngine()
        engine.add_rule(DeconflictionRule(
            rule_id="R1", rule_type="temporal",
            parameters={"min_interval_seconds": 0},
        ))
        engine.add_rule(DeconflictionRule(
            rule_id="R2", rule_type="spatial",
            parameters={"min_distance_meters": 100},
        ))
        result = engine.check_deconfliction("T1", "S1", "W1")
        assert result.is_clear is True

    def test_different_targets_no_conflict(self):
        engine = DeconflictionEngine()
        engine.add_rule(DeconflictionRule(
            rule_id="R1", rule_type="temporal",
            parameters={"min_interval_seconds": 30},
        ))
        engine.record_engagement("T1", "S1", "W1")
        # Different target should be clear
        result = engine.check_deconfliction("T2", "S1", "W1")
        assert result.is_clear is True


# ---------------------------------------------------------------------------
# EngagePhase Integration Tests
# ---------------------------------------------------------------------------

class TestEngagePhase:
    """Integration tests for the full engage phase."""

    def test_engage_phase_initialization(self):
        phase = EngagePhase()
        assert phase.assigner is not None
        assert phase.authorizer is not None
        assert phase.deconfliction is not None

    def test_full_engagement_workflow(self):
        phase = EngagePhase()
        # Setup
        phase.assigner.register_weapon("W1", WeaponType.MISSILE, set())
        phase.assigner.register_shooter("S1", {"missile"})
        phase.assigner.register_target("T1")
        phase.authorizer.authorize("T1", "A1", "explicit")

        # Assign
        assign_result = phase.assigner.assign("T1", "W1", "S1")
        assert assign_result.success

        # Authorize
        auth_result = phase.authorizer.check_authorization("T1")
        assert auth_result.authorized

        # Deconflict
        deconf_result = phase.deconfliction.check_deconfliction("T1", "S1", "W1")
        assert deconf_result.is_clear

    def test_engagement_blocked_by_authorization(self):
        phase = EngagePhase()
        phase.assigner.register_weapon("W1", WeaponType.MISSILE, set())
        phase.assigner.register_shooter("S1", {"missile"})
        # No authorization
        auth_result = phase.authorizer.check_authorization("T1")
        assert not auth_result.authorized

    def test_engagement_blocked_by_deconfliction(self):
        phase = EngagePhase()
        phase.assigner.register_weapon("W1", WeaponType.MISSILE, set())
        phase.assigner.register_shooter("S1", {"missile"})
        phase.authorizer.authorize("T1", "A1", "explicit")
        phase.deconfliction.add_rule(DeconflictionRule(
            rule_id="R1", rule_type="temporal",
            parameters={"min_interval_seconds": 30},
        ))
        # First engagement
        phase.deconfliction.record_engagement("T1", "S1", "W1")
        # Second should be blocked
        result = phase.deconfliction.check_deconfliction("T1", "S1", "W1")
        assert not result.is_clear

    def test_auto_assign_and_authorize(self):
        phase = EngagePhase()
        phase.assigner.register_weapon("W1", WeaponType.MISSILE, set())
        phase.assigner.register_shooter("S1", {"missile"})
        phase.authorizer.authorize("T1", "A1", "explicit")

        result = phase.assigner.auto_assign(["T1"])
        assert len(result.assignments) == 1

    def test_engage_phase_clear_all(self):
        phase = EngagePhase()
        phase.assigner.register_weapon("W1", WeaponType.MISSILE, set())
        phase.assigner.register_shooter("S1", {"missile"})
        phase.assigner.register_target("T1")
        phase.authorizer.authorize("T1", "A1", "explicit")
        phase.assigner.assign("T1", "W1", "S1")

        phase.clear_all()
        assert len(phase.assigner.active_assignments) == 0
        assert not phase.authorizer.is_authorized("T1")

    def test_assignment_result_str(self):
        result = AssignmentResult(
            success=True,
            assignment=WeaponTargetAssignment(
                weapon_id="W1", target_id="T1", shooter_id="S1",
                weapon_type=WeaponType.MISSILE,
            ),
        )
        s = str(result)
        assert "success" in s.lower() or "W1" in s

    def test_authorization_result_str(self):
        result = AuthorizationResult(
            target_id="T1",
            authorized=True,
            authorization_type="explicit",
        )
        s = str(result)
        assert "T1" in s

    def test_deconfliction_result_str(self):
        result = DeconflictionResult(
            is_clear=True,
            target_id="T1",
        )
        s = str(result)
        assert "T1" in s


# ---------------------------------------------------------------------------
# Edge Cases and Boundary Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_weapon_with_empty_capabilities(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", set())
        assigner.register_target("T1")
        result = assigner.assign("T1", "W1", "S1")
        assert result.success

    def test_shooter_with_zero_capacity(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_shooter("S1", {"missile"}, max_weapons=0)
        assigner.register_target("T1")
        with pytest.raises(EngagePhaseError):
            assigner.assign("T1", "W1", "S1")

    def test_authorization_with_empty_authorizer_id(self):
        authorizer = EngagementAuthorizer()
        authorizer.authorize("T1", "", "explicit")
        assert authorizer.is_authorized("T1")

    def test_deconfliction_with_no_rules(self):
        engine = DeconflictionEngine()
        result = engine.check_deconfliction("T1", "S1", "W1")
        assert result.is_clear is True

    def test_multiple_weapons_one_target(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.MISSILE, set())
        assigner.register_weapon("W2", WeaponType.GUN, set())
        assigner.register_shooter("S1", {"missile", "gun"}, max_weapons=2)
        assigner.register_target("T1")
        r1 = assigner.assign("T1", "W1", "S1")
        r2 = assigner.assign("T1", "W2", "S1")
        assert r1.success
        assert r2.success

    def test_weapon_type_laser(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.LASER, set())
        assigner.register_shooter("S1", {"laser"})
        assigner.register_target("T1")
        result = assigner.assign("T1", "W1", "S1")
        assert result.success

    def test_weapon_type_electronic_warfare(self):
        assigner = WeaponTargetAssigner()
        assigner.register_weapon("W1", WeaponType.ELECTRONIC_WARFARE, set())
        assigner.register_shooter("S1", {"electronic_warfare"})
        assigner.register_target("T1")
        result = assigner.assign("T1", "W1", "S1")
        assert result.success
