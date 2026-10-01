"""JADC2 Integration Tests — Full F2T2EA Lifecycle.

Tests the complete Find-Fix-Track-Target-Engage-Assess kill chain
including human governance, latency optimization, and state transitions.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from src.c2.f2t2ea import (
    AssessmentResult,
    EngagementOutcome,
    EngagementResult,
    F2T2EAChain,
    F2T2EAConfig,
    F2T2EAError,
    F2T2EAPhase,
    HumanDecision,
    HumanGovernance,
    HumanGovernanceError,
    KillChainStatus,
    LatencyBudget,
    LatencyOptimizer,
    SensorReading,
    Shooter,
    Target,
    ThreatLevel,
    Track,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reading(
    sensor_id: str = "sensor-1",
    confidence: float = 0.95,
    classification: str = "hostile",
    location: tuple[float, float] = (34.0, 45.0),
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        timestamp=datetime.now(timezone.utc),
        location=location,
        confidence=confidence,
        classification=classification,
    )


def _make_chain(
    require_human_authorization: bool = False,
    max_latency_ms: float = 5000,
) -> F2T2EAChain:
    config = F2T2EAConfig(
        max_latency_ms=max_latency_ms,
        require_human_authorization=require_human_authorization,
    )
    return F2T2EAChain(config=config)


def _make_governance(require_dual_for_critical: bool = False) -> HumanGovernance:
    return HumanGovernance(require_dual_for_critical=require_dual_for_critical)


def _advance_to_phase(chain: F2T2EAChain, phase: F2T2EAPhase) -> None:
    """Advance chain to a specific phase, executing required steps."""
    phase_order = list(F2T2EAPhase)
    current_idx = phase_order.index(chain.state.current_phase)
    target_idx = phase_order.index(phase)

    for i in range(current_idx, target_idx):
        current = phase_order[i]
        if current == F2T2EAPhase.FIND:
            chain.confirm_find()
        elif current == F2T2EAPhase.FIX:
            chain.confirm_fix()
        elif current == F2T2EAPhase.TRACK:
            chain.confirm_track()
        elif current == F2T2EAPhase.TARGET:
            chain.confirm_target()
        elif current == F2T2EAPhase.ENGAGE:
            chain.confirm_engage()


# ---------------------------------------------------------------------------
# Test 1: Full F2T2EA Lifecycle — Happy Path
# ---------------------------------------------------------------------------


class TestFullF2T2EALifecycle:
    """Integration test: complete F2T2EA cycle from FIND to ASSESS."""

    def test_full_lifecycle_success(self):
        """Execute the full kill chain and verify final state."""
        chain = _make_chain()
        governance = _make_governance()
        chain.governance = governance

        # FIND: Submit sensor readings
        for i in range(5):
            chain.submit_sensor_reading(
                _make_reading(sensor_id=f"sensor-{i}", confidence=0.95)
            )
        assert chain.state.threat_level == ThreatLevel.CRITICAL
        chain.confirm_find()
        assert chain.state.current_phase == F2T2EAPhase.FIX

        # FIX: Fix target location
        target = chain.fix_target(
            location=(34.05, 45.05),
            target_id="TGT-001",
            classification="armor",
        )
        assert target.target_id == "TGT-001"
        assert target.threat_level == ThreatLevel.CRITICAL
        chain.confirm_fix()
        assert chain.state.current_phase == F2T2EAPhase.TRACK

        # TRACK: Start and update track
        track = chain.start_tracking("TGT-001", "TRK-001")
        assert track.track_id == "TRK-001"
        chain.update_track("TRK-001", (34.06, 45.06))
        chain.confirm_track()
        assert chain.state.current_phase == F2T2EAPhase.TARGET

        # TARGET: Authorize engagement (target already added via fix_target)
        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        chain.confirm_target()
        assert chain.state.current_phase == F2T2EAPhase.ENGAGE

        # ENGAGE: Execute engagement
        result = chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)
        assert result.outcome == EngagementOutcome.SUCCESS
        assert chain.get_target("TGT-001").destroyed is True
        chain.confirm_engage()
        assert chain.state.current_phase == F2T2EAPhase.ASSESS

        # ASSESS: Battle damage assessment
        assessment = chain.assess("TGT-001", effectiveness=0.9, collateral_damage=False)
        assert assessment.effectiveness == 0.9
        assert assessment.requires_re_engagement is False
        chain.confirm_assess()

        # Verify final state
        assert chain.state.status == KillChainStatus.COMPLETE
        assert chain.state.is_terminal() is True


# ---------------------------------------------------------------------------
# Test 2: FIND Phase — Sensor Reading Accumulation
# ---------------------------------------------------------------------------


class TestFindPhase:
    """Integration test: FIND phase sensor reading accumulation."""

    def test_multiple_sensor_readings_accumulate(self):
        """Multiple sensor readings are stored and threat level updates."""
        chain = _make_chain()

        for i in range(3):
            chain.submit_sensor_reading(
                _make_reading(sensor_id=f"sensor-{i}", confidence=0.6)
            )

        assert len(chain._sensor_readings) == 3
        assert chain.state.threat_level == ThreatLevel.MEDIUM

    def test_threat_level_escalation(self):
        """Threat level escalates with more high-confidence readings."""
        chain = _make_chain()

        # Start with low confidence
        chain.submit_sensor_reading(_make_reading(confidence=0.3))
        assert chain.state.threat_level == ThreatLevel.LOW

        # Add medium confidence
        chain.submit_sensor_reading(_make_reading(confidence=0.6))
        assert chain.state.threat_level == ThreatLevel.MEDIUM

        # Add high confidence
        chain.submit_sensor_reading(_make_reading(confidence=0.85))
        assert chain.state.threat_level == ThreatLevel.HIGH

        # Add many high confidence readings -> CRITICAL
        for i in range(5):
            chain.submit_sensor_reading(
                _make_reading(sensor_id=f"sensor-{i}", confidence=0.95)
            )
        assert chain.state.threat_level == ThreatLevel.CRITICAL


# ---------------------------------------------------------------------------
# Test 3: FIX Phase — Target Creation
# ---------------------------------------------------------------------------


class TestFixPhase:
    """Integration test: FIX phase target creation and validation."""

    def test_fix_target_creates_target(self):
        """fix_target creates a target with current threat level."""
        chain = _make_chain()
        chain.submit_sensor_reading(_make_reading(confidence=0.9))
        chain.confirm_find()

        target = chain.fix_target((34.0, 45.0), "TGT-001", "infantry")
        assert target.target_id == "TGT-001"
        assert target.location == (34.0, 45.0)
        assert target.threat_level == ThreatLevel.HIGH
        assert target.classification == "infantry"
        assert target.destroyed is False

    def test_fix_target_requires_location(self):
        """fix_target raises error when location is None."""
        chain = _make_chain()
        chain.confirm_find()

        with pytest.raises(F2T2EAError, match="location is required"):
            chain.fix_target(None, "TGT-001", "armor")


# ---------------------------------------------------------------------------
# Test 4: TRACK Phase — Track Staleness
# ---------------------------------------------------------------------------


class TestTrackPhase:
    """Integration test: TRACK phase track management and staleness."""

    def test_track_staleness_detection(self):
        """Track becomes stale after timeout."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.TRACK)

        track = chain.start_tracking("TGT-001", "TRK-001")
        assert track.is_stale(timeout_seconds=1.0) is False

        # Manually set last_update to past
        track.last_update = datetime.now(timezone.utc) - timedelta(seconds=2)
        assert track.is_stale(timeout_seconds=1.0) is True

    def test_update_track_refreshes_position(self):
        """update_track updates position and timestamp."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.TRACK)

        chain.start_tracking("TGT-001", "TRK-001")
        chain.update_track("TRK-001", (35.0, 46.0))

        track = chain.get_track("TRK-001")
        assert track.latest_position == (35.0, 46.0)

    def test_update_unknown_track_raises(self):
        """update_track raises for unknown track ID."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.TRACK)

        with pytest.raises(F2T2EAError, match="Unknown track"):
            chain.update_track("NONEXISTENT", (0.0, 0.0))


# ---------------------------------------------------------------------------
# Test 5: TARGET Phase — Target Prioritization
# ---------------------------------------------------------------------------


class TestTargetPhase:
    """Integration test: TARGET phase target management."""

    def test_target_prioritization_by_threat(self):
        """Targets are sorted by threat level (highest first)."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.TARGET)

        chain.add_target(
            Target("TGT-LOW", (1.0, 1.0), ThreatLevel.LOW)
        )
        chain.add_target(
            Target("TGT-CRIT", (2.0, 2.0), ThreatLevel.CRITICAL)
        )
        chain.add_target(
            Target("TGT-MED", (3.0, 3.0), ThreatLevel.MEDIUM)
        )

        prioritized = chain.prioritize_targets()
        assert [t.target_id for t in prioritized] == [
            "TGT-CRIT",
            "TGT-MED",
            "TGT-LOW",
        ]

    def test_duplicate_target_raises(self):
        """Adding duplicate target ID raises error."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.TARGET)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.LOW))
        with pytest.raises(F2T2EAError, match="Duplicate target"):
            chain.add_target(Target("TGT-001", (2.0, 2.0), ThreatLevel.HIGH))


# ---------------------------------------------------------------------------
# Test 6: ENGAGE Phase — Authorization Required
# ---------------------------------------------------------------------------


class TestEngagePhaseAuthorization:
    """Integration test: ENGAGE phase authorization enforcement."""

    def test_engage_requires_authorization(self):
        """Engagement fails without human authorization."""
        chain = _make_chain()
        governance = _make_governance()
        chain.governance = governance
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))

        with pytest.raises(HumanGovernanceError, match="not authorized"):
            chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)

    def test_engage_succeeds_with_authorization(self):
        """Engagement succeeds when authorized."""
        chain = _make_chain()
        governance = _make_governance()
        chain.governance = governance
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))
        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")

        result = chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)
        assert result.outcome == EngagementOutcome.SUCCESS
        assert result.shooter_id == "shooter-1"

    def test_engage_veto_blocks_engagement(self):
        """Veto prevents engagement even with authorization."""
        chain = _make_chain()
        governance = _make_governance()
        chain.governance = governance
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))
        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        governance.veto(HumanDecision.ENGAGE, "commander-2", "TGT-001")

        with pytest.raises(HumanGovernanceError, match="vetoed"):
            chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)


# ---------------------------------------------------------------------------
# Test 7: ENGAGE Phase — Engagement Outcomes
# ---------------------------------------------------------------------------


class TestEngagePhaseOutcomes:
    """Integration test: ENGAGE phase outcome handling."""

    def test_successful_engagement_marks_destroyed(self):
        """Successful engagement marks target as destroyed."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))
        chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)

        assert chain.get_target("TGT-001").destroyed is True

    def test_failed_engagement_does_not_destroy(self):
        """Failed engagement does not mark target as destroyed."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))
        chain.engage("TGT-001", "shooter-1", EngagementOutcome.FAILURE)

        assert chain.get_target("TGT-001").destroyed is False

    def test_partial_engagement_does_not_destroy(self):
        """Partial engagement does not mark target as destroyed."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))
        chain.engage("TGT-001", "shooter-1", EngagementOutcome.PARTIAL)

        assert chain.get_target("TGT-001").destroyed is False


# ---------------------------------------------------------------------------
# Test 8: ASSESS Phase — Battle Damage Assessment
# ---------------------------------------------------------------------------


class TestAssessPhase:
    """Integration test: ASSESS phase battle damage assessment."""

    def test_assess_effectiveness_validation(self):
        """Effectiveness must be between 0 and 1."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ASSESS)

        with pytest.raises(ValueError, match="between 0 and 1"):
            chain.assess("TGT-001", effectiveness=1.5, collateral_damage=False)

        with pytest.raises(ValueError, match="between 0 and 1"):
            chain.assess("TGT-001", effectiveness=-0.1, collateral_damage=False)

    def test_assess_re_engagement_flag(self):
        """Low effectiveness triggers re-engagement flag."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ASSESS)

        result = chain.assess("TGT-001", effectiveness=0.3, collateral_damage=False)
        assert result.requires_re_engagement is True

        result = chain.assess("TGT-001", effectiveness=0.7, collateral_damage=False)
        assert result.requires_re_engagement is False

    def test_assess_collateral_damage_recorded(self):
        """Collateral damage flag is recorded."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ASSESS)

        result = chain.assess("TGT-001", effectiveness=0.8, collateral_damage=True)
        assert result.collateral_damage is True


# ---------------------------------------------------------------------------
# Test 9: Human Governance — Dual Authorization
# ---------------------------------------------------------------------------


class TestHumanGovernanceDualAuth:
    """Integration test: dual authorization for critical threats."""

    def test_dual_authorization_required_for_critical(self):
        """Critical threats require two authorizations."""
        governance = _make_governance(require_dual_for_critical=True)

        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        assert governance.is_authorized(
            HumanDecision.ENGAGE, "TGT-001", ThreatLevel.CRITICAL
        ) is False

        governance.authorize(HumanDecision.ENGAGE, "commander-2", "TGT-001")
        assert governance.is_authorized(
            HumanDecision.ENGAGE, "TGT-001", ThreatLevel.CRITICAL
        ) is True

    def test_single_authorization_sufficient_for_non_critical(self):
        """Non-critical threats need only one authorization."""
        governance = _make_governance(require_dual_for_critical=True)

        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        assert governance.is_authorized(
            HumanDecision.ENGAGE, "TGT-001", ThreatLevel.HIGH
        ) is True


# ---------------------------------------------------------------------------
# Test 10: Human Governance — Audit Trail
# ---------------------------------------------------------------------------


class TestHumanGovernanceAuditTrail:
    """Integration test: audit trail records all decisions."""

    def test_audit_trail_records_authorize_and_veto(self):
        """Audit trail captures both authorize and veto actions."""
        governance = _make_governance()

        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        governance.veto(HumanDecision.ENGAGE, "commander-2", "TGT-002")

        trail = governance.get_audit_trail()
        assert len(trail) == 2
        assert trail[0].action == "authorize"
        assert trail[0].actor_id == "commander-1"
        assert trail[1].action == "veto"
        assert trail[1].actor_id == "commander-2"


# ---------------------------------------------------------------------------
# Test 11: Latency Budget — Phase Tracking
# ---------------------------------------------------------------------------


class TestLatencyBudget:
    """Integration test: latency budget tracking across phases."""

    def test_latency_budget_tracks_phases(self):
        """Latency budget records per-phase latency."""
        budget = LatencyBudget(threshold_ms=1000)

        budget.record(F2T2EAPhase.FIND, 0.1)
        budget.record(F2T2EAPhase.FIX, 0.2)
        budget.record(F2T2EAPhase.TRACK, 0.3)

        assert budget.total() == pytest.approx(0.6)
        assert budget.is_exceeded() is False

        budget.record(F2T2EAPhase.TARGET, 0.5)
        assert budget.is_exceeded() is True

    def test_latency_budget_phase_breakdown(self):
        """Phase breakdown returns per-phase latencies."""
        budget = LatencyBudget(threshold_ms=1000)

        budget.record(F2T2EAPhase.FIND, 0.1)
        budget.record(F2T2EAPhase.FIX, 0.2)

        breakdown = budget.phase_breakdown()
        assert breakdown[F2T2EAPhase.FIND] == pytest.approx(0.1)
        assert breakdown[F2T2EAPhase.FIX] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Test 12: Latency Optimizer — Shooter Selection
# ---------------------------------------------------------------------------


class TestLatencyOptimizer:
    """Integration test: latency optimizer shooter selection."""

    def test_select_fastest_shooter(self):
        """Optimizer selects shooter with lowest latency."""
        optimizer = LatencyOptimizer()
        optimizer.register_shooter(Shooter("slow", latency_ms=200.0))
        optimizer.register_shooter(Shooter("fast", latency_ms=50.0))
        optimizer.register_shooter(Shooter("medium", latency_ms=100.0))

        selected = optimizer.select_shooter()
        assert selected.shooter_id == "fast"

    def test_select_shooter_by_capability(self):
        """Optimizer filters shooters by required capability."""
        optimizer = LatencyOptimizer()
        optimizer.register_shooter(
            Shooter("artillery", latency_ms=100.0, capabilities={"artillery"})
        )
        optimizer.register_shooter(
            Shooter("air", latency_ms=50.0, capabilities={"air"})
        )

        selected = optimizer.select_shooter(required_capability="air")
        assert selected.shooter_id == "air"

    def test_select_shooter_no_match_raises(self):
        """Optimizer raises when no shooter matches capability."""
        optimizer = LatencyOptimizer()
        optimizer.register_shooter(
            Shooter("artillery", latency_ms=100.0, capabilities={"artillery"})
        )

        with pytest.raises(F2T2EAError, match="No suitable shooter"):
            optimizer.select_shooter(required_capability="naval")

    def test_update_latency(self):
        """Shooter latency can be updated."""
        optimizer = LatencyOptimizer()
        optimizer.register_shooter(Shooter("shooter-1", latency_ms=100.0))

        optimizer.update_latency("shooter-1", 75.0)
        assert optimizer._shooters["shooter-1"].latency_ms == 75.0


# ---------------------------------------------------------------------------
# Test 13: State Transitions — Restart
# ---------------------------------------------------------------------------


class TestStateTransitions:
    """Integration test: state transition behaviors."""

    def test_restart_clears_all_state(self):
        """Restart clears targets, tracks, engagements, and assessments."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        chain.add_target(Target("TGT-001", (1.0, 1.0), ThreatLevel.HIGH))
        chain.start_tracking("TGT-001", "TRK-001")
        chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)
        chain.confirm_engage()
        chain.assess("TGT-001", effectiveness=0.9, collateral_damage=False)

        chain.restart()

        assert chain.state.current_phase == F2T2EAPhase.FIND
        assert chain.state.status == KillChainStatus.ACTIVE
        assert len(chain._targets) == 0
        assert len(chain._tracks) == 0
        assert len(chain._engagements) == 0
        assert len(chain._assessments) == 0

    def test_abort_requires_reason_in_find_phase(self):
        """Abort requires a reason when in FIND phase."""
        chain = _make_chain()

        with pytest.raises(F2T2EAError, match="reason"):
            chain.abort()

    def test_abort_with_reason_succeeds(self):
        """Abort with reason succeeds."""
        chain = _make_chain()
        chain.abort(reason="Target lost")
        assert chain.state.status == KillChainStatus.ABORTED

    def test_cannot_revisit_completed_phase(self):
        """Cannot advance to a previously completed phase."""
        chain = _make_chain()
        chain.confirm_find()

        with pytest.raises(F2T2EAError, match="Cannot revisit"):
            chain.advance_to(F2T2EAPhase.FIND)

    def test_cannot_advance_terminal_chain(self):
        """Cannot advance a chain that has reached terminal state."""
        chain = _make_chain()
        chain.abort(reason="Test abort")

        with pytest.raises(F2T2EAError, match="terminal"):
            chain.advance_to(F2T2EAPhase.FIX)


# ---------------------------------------------------------------------------
# Test 14: Phase Transition Validation
# ---------------------------------------------------------------------------


class TestPhaseTransitionValidation:
    """Integration test: phase transition validation."""

    def test_confirm_find_requires_find_phase(self):
        """confirm_find only works in FIND phase."""
        chain = _make_chain()
        chain.confirm_find()

        with pytest.raises(F2T2EAError, match="Must be in FIND phase"):
            chain.confirm_find()

    def test_confirm_fix_requires_fix_phase(self):
        """confirm_fix only works in FIX phase."""
        chain = _make_chain()

        with pytest.raises(F2T2EAError, match="Must be in FIX phase"):
            chain.confirm_fix()

    def test_confirm_track_requires_track_phase(self):
        """confirm_track only works in TRACK phase."""
        chain = _make_chain()

        with pytest.raises(F2T2EAError, match="Must be in TRACK phase"):
            chain.confirm_track()

    def test_confirm_target_requires_target_phase(self):
        """confirm_target only works in TARGET phase."""
        chain = _make_chain()

        with pytest.raises(F2T2EAError, match="Must be in TARGET phase"):
            chain.confirm_target()

    def test_confirm_engage_requires_engage_phase(self):
        """confirm_engage only works in ENGAGE phase."""
        chain = _make_chain()

        with pytest.raises(F2T2EAError, match="Must be in ENGAGE phase"):
            chain.confirm_engage()


# ---------------------------------------------------------------------------
# Test 15: Engagement with Unknown Target
# ---------------------------------------------------------------------------


class TestEngageUnknownTarget:
    """Integration test: engagement with unknown target."""

    def test_engage_unknown_target_raises(self):
        """Engaging an unknown target raises error."""
        chain = _make_chain()
        _advance_to_phase(chain, F2T2EAPhase.ENGAGE)

        with pytest.raises(F2T2EAError, match="Unknown target"):
            chain.engage("NONEXISTENT", "shooter-1", EngagementOutcome.SUCCESS)


# ---------------------------------------------------------------------------
# Test 16: F2T2EAConfig Validation
# ---------------------------------------------------------------------------


class TestF2T2EAConfig:
    """Integration test: configuration validation."""

    def test_config_max_latency_must_be_positive(self):
        """max_latency_ms must be positive."""
        with pytest.raises(ValueError, match="positive"):
            F2T2EAConfig(max_latency_ms=0)

        with pytest.raises(ValueError, match="positive"):
            F2T2EAConfig(max_latency_ms=-100)


# ---------------------------------------------------------------------------
# Test 17: F2T2EAState Elapsed Time
# ---------------------------------------------------------------------------


class TestF2T2EAState:
    """Integration test: state elapsed time tracking."""

    def test_elapsed_seconds_increases(self):
        """Elapsed seconds increases over time."""
        chain = _make_chain()
        initial = chain.state.elapsed_seconds()
        time.sleep(0.01)
        later = chain.state.elapsed_seconds()
        assert later > initial

    def test_is_terminal_false_when_active(self):
        """is_terminal returns False when chain is active."""
        chain = _make_chain()
        assert chain.state.is_terminal() is False

    def test_is_terminal_true_when_complete(self):
        """is_terminal returns True when chain is complete."""
        chain = _make_chain()
        chain.confirm_assess()
        assert chain.state.is_terminal() is True


# ---------------------------------------------------------------------------
# Test 18: F2T2EAPhase Next
# ---------------------------------------------------------------------------


class TestF2T2EAPhaseNext:
    """Integration test: phase next() navigation."""

    def test_next_phase_sequence(self):
        """Each phase returns the correct next phase."""
        assert F2T2EAPhase.FIND.next() == F2T2EAPhase.FIX
        assert F2T2EAPhase.FIX.next() == F2T2EAPhase.TRACK
        assert F2T2EAPhase.TRACK.next() == F2T2EAPhase.TARGET
        assert F2T2EAPhase.TARGET.next() == F2T2EAPhase.ENGAGE
        assert F2T2EAPhase.ENGAGE.next() == F2T2EAPhase.ASSESS

    def test_next_returns_none_for_last_phase(self):
        """ASSESS phase has no next phase."""
        assert F2T2EAPhase.ASSESS.next() is None


# ---------------------------------------------------------------------------
# Test 19: Human Governance TTL Expiration
# ---------------------------------------------------------------------------


class TestHumanGovernanceTTL:
    """Integration test: authorization TTL expiration."""

    def test_authorization_expires_after_ttl(self):
        """Authorization expires after TTL."""
        governance = _make_governance()
        governance.authorize(
            HumanDecision.ENGAGE, "commander-1", "TGT-001", ttl_seconds=0.05
        )
        assert governance.is_authorized(HumanDecision.ENGAGE, "TGT-001") is True

        time.sleep(0.1)
        assert governance.is_authorized(HumanDecision.ENGAGE, "TGT-001") is False

    def test_authorization_without_ttl_persists(self):
        """Authorization without TTL does not expire."""
        governance = _make_governance()
        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        assert governance.is_authorized(HumanDecision.ENGAGE, "TGT-001") is True


# ---------------------------------------------------------------------------
# Test 20: Full Lifecycle with Governance and Latency
# ---------------------------------------------------------------------------


class TestFullLifecycleWithGovernanceAndLatency:
    """Integration test: full lifecycle with governance and latency tracking."""

    def test_full_lifecycle_with_governance_and_latency(self):
        """Complete lifecycle with governance authorization and latency tracking."""
        config = F2T2EAConfig(max_latency_ms=5000, require_human_authorization=True)
        governance = _make_governance(require_dual_for_critical=True)
        chain = F2T2EAChain(config=config, governance=governance)

        # FIND
        for i in range(5):
            chain.submit_sensor_reading(
                _make_reading(sensor_id=f"sensor-{i}", confidence=0.95)
            )
        assert chain.state.threat_level == ThreatLevel.CRITICAL
        chain.confirm_find()

        # FIX
        target = chain.fix_target((34.0, 45.0), "TGT-001", "armor")
        chain.confirm_fix()

        # TRACK
        chain.start_tracking("TGT-001", "TRK-001")
        chain.update_track("TRK-001", (34.1, 45.1))
        chain.confirm_track()

        # TARGET (target already added via fix_target)
        # Dual authorization for critical threat
        governance.authorize(HumanDecision.ENGAGE, "commander-1", "TGT-001")
        governance.authorize(HumanDecision.ENGAGE, "commander-2", "TGT-001")
        chain.confirm_target()

        # ENGAGE
        result = chain.engage("TGT-001", "shooter-1", EngagementOutcome.SUCCESS)
        assert result.outcome == EngagementOutcome.SUCCESS
        chain.confirm_engage()

        # ASSESS
        assessment = chain.assess("TGT-001", effectiveness=0.85, collateral_damage=False)
        assert assessment.requires_re_engagement is False
        chain.confirm_assess()

        # Verify
        assert chain.state.status == KillChainStatus.COMPLETE
        assert chain.get_target("TGT-001").destroyed is True
        assert len(governance.get_audit_trail()) == 2
