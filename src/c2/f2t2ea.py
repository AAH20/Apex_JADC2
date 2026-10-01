"""Defense C2 F2T2EA Kill Chain Core.

Find-Fix-Track-Target-Engage-Assess (F2T2EA) kill chain implementation
with sensor-to-shooter latency optimization and human governance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class F2T2EAError(Exception):
    """Base exception for F2T2EA operations."""


class HumanGovernanceError(F2T2EAError):
    """Raised when human governance checks fail."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class F2T2EAPhase(str, Enum):
    """F2T2EA kill chain phases."""

    FIND = "find"
    FIX = "fix"
    TRACK = "track"
    TARGET = "target"
    ENGAGE = "engage"
    ASSESS = "assess"

    def next(self) -> Optional[F2T2EAPhase]:
        """Return the next phase in the kill chain."""
        phases = list(F2T2EAPhase)
        idx = phases.index(self)
        if idx < len(phases) - 1:
            return phases[idx + 1]
        return None


class ThreatLevel(int, Enum):
    """Threat severity levels."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class KillChainStatus(str, Enum):
    """Kill chain execution status."""

    ACTIVE = "active"
    COMPLETE = "complete"
    ABORTED = "aborted"


class EngagementOutcome(str, Enum):
    """Engagement result outcomes."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class HumanDecision(str, Enum):
    """Types of human decisions."""

    ENGAGE = "engage"
    ABORT = "abort"
    RESTART = "restart"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class SensorReading:
    """A sensor detection reading."""

    sensor_id: str
    timestamp: datetime
    location: tuple[float, float]
    confidence: float
    classification: str


@dataclass
class Target:
    """A tracked target."""

    target_id: str
    location: tuple[float, float]
    threat_level: ThreatLevel
    classification: str = ""
    destroyed: bool = False


@dataclass
class Track:
    """A target track."""

    track_id: str
    target_id: str
    latest_position: Optional[tuple[float, float]] = None
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_stale(self, timeout_seconds: float) -> bool:
        """Check if the track has gone stale."""
        elapsed = (datetime.now(timezone.utc) - self.last_update).total_seconds()
        return elapsed > timeout_seconds


@dataclass
class Shooter:
    """An engagement shooter."""

    shooter_id: str
    latency_ms: float
    capabilities: set[str] = field(default_factory=set)


@dataclass
class EngagementResult:
    """Result of an engagement."""

    target_id: str
    shooter_id: str
    outcome: EngagementOutcome
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AssessmentResult:
    """Result of a battle damage assessment."""

    target_id: str
    effectiveness: float
    collateral_damage: bool
    requires_re_engagement: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SensorToShooterLink:
    """Link between a sensor and a shooter."""

    sensor_id: str
    shooter_id: str
    latency_ms: float


@dataclass
class F2T2EAConfig:
    """Configuration for the F2T2EA chain."""

    max_latency_ms: float = 5000
    require_human_authorization: bool = True
    auto_advance: bool = False

    def __post_init__(self):
        if self.max_latency_ms <= 0:
            raise ValueError("max_latency_ms must be positive")


@dataclass
class F2T2EAState:
    """Current state of the F2T2EA chain."""

    current_phase: F2T2EAPhase = F2T2EAPhase.FIND
    threat_level: ThreatLevel = ThreatLevel.LOW
    status: KillChainStatus = KillChainStatus.ACTIVE
    history: list[tuple[datetime, F2T2EAPhase]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def elapsed_seconds(self) -> float:
        """Return elapsed time since chain creation."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    def is_terminal(self) -> bool:
        """Check if the chain has reached a terminal state."""
        return self.status in (KillChainStatus.COMPLETE, KillChainStatus.ABORTED)


# ---------------------------------------------------------------------------
# Latency Budget
# ---------------------------------------------------------------------------


class LatencyBudget:
    """Tracks latency across kill chain phases."""

    def __init__(self, threshold_ms: float = 500):
        self.threshold_ms = threshold_ms
        self._records: dict[F2T2EAPhase, float] = {}

    def record(self, phase: F2T2EAPhase, seconds: float) -> None:
        """Record latency for a phase."""
        self._records[phase] = seconds

    def total(self) -> float:
        """Return total recorded latency in seconds."""
        return sum(self._records.values())

    def is_exceeded(self) -> bool:
        """Check if total latency exceeds threshold."""
        return self.total() * 1000 > self.threshold_ms

    def phase_breakdown(self) -> dict[F2T2EAPhase, float]:
        """Return per-phase latency breakdown."""
        return dict(self._records)


# ---------------------------------------------------------------------------
# Latency Optimizer
# ---------------------------------------------------------------------------


class LatencyOptimizer:
    """Optimizes sensor-to-shooter latency."""

    def __init__(self):
        self._shooters: dict[str, Shooter] = {}

    def register_shooter(self, shooter: Shooter) -> None:
        """Register a shooter."""
        self._shooters[shooter.shooter_id] = shooter

    def select_shooter(self, required_capability: Optional[str] = None) -> Shooter:
        """Select the fastest shooter, optionally filtered by capability."""
        candidates = list(self._shooters.values())
        if required_capability is not None:
            candidates = [s for s in candidates if required_capability in s.capabilities]
        if not candidates:
            raise F2T2EAError("No suitable shooter available")
        return min(candidates, key=lambda s: s.latency_ms)

    def update_latency(self, shooter_id: str, latency_ms: float) -> None:
        """Update a shooter's latency."""
        if shooter_id not in self._shooters:
            raise F2T2EAError(f"Unknown shooter: {shooter_id}")
        self._shooters[shooter_id].latency_ms = latency_ms


# ---------------------------------------------------------------------------
# Human Governance
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    """An audit trail entry."""

    decision_type: HumanDecision
    actor_id: str
    target_id: str
    timestamp: datetime
    action: str


class HumanGovernance:
    """Human governance and authorization controls."""

    def __init__(self, require_dual_for_critical: bool = False):
        self.require_dual_for_critical = require_dual_for_critical
        self._authorizations: dict[tuple[HumanDecision, str], list[tuple[str, datetime, Optional[float]]]] = {}
        self._vetoes: dict[tuple[HumanDecision, str], list[tuple[str, datetime, Optional[float]]]] = {}
        self._audit_trail: list[AuditEntry] = []

    def authorize(
        self,
        decision_type: HumanDecision,
        authorizer_id: str,
        target_id: str,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Authorize a decision."""
        key = (decision_type, target_id)
        if key not in self._authorizations:
            self._authorizations[key] = []
        self._authorizations[key].append((authorizer_id, datetime.now(timezone.utc), ttl_seconds))
        self._audit_trail.append(AuditEntry(
            decision_type=decision_type,
            actor_id=authorizer_id,
            target_id=target_id,
            timestamp=datetime.now(timezone.utc),
            action="authorize",
        ))

    def veto(
        self,
        decision_type: HumanDecision,
        vetoer_id: str,
        target_id: str,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Veto a decision."""
        key = (decision_type, target_id)
        if key not in self._vetoes:
            self._vetoes[key] = []
        self._vetoes[key].append((vetoer_id, datetime.now(timezone.utc), ttl_seconds))
        self._audit_trail.append(AuditEntry(
            decision_type=decision_type,
            actor_id=vetoer_id,
            target_id=target_id,
            timestamp=datetime.now(timezone.utc),
            action="veto",
        ))

    def is_authorized(
        self,
        decision_type: HumanDecision,
        target_id: str,
        threat_level: Optional[ThreatLevel] = None,
    ) -> bool:
        """Check if a decision is authorized."""
        key = (decision_type, target_id)
        if key not in self._authorizations:
            return False
        now = datetime.now(timezone.utc)
        valid = [
            (actor, ts, ttl) for actor, ts, ttl in self._authorizations[key]
            if ttl is None or (now - ts).total_seconds() < ttl
        ]
        if not valid:
            return False
        if self.require_dual_for_critical and threat_level == ThreatLevel.CRITICAL:
            return len(valid) >= 2
        return True

    def is_vetoed(self, decision_type: HumanDecision, target_id: str) -> bool:
        """Check if a decision is vetoed."""
        key = (decision_type, target_id)
        if key not in self._vetoes:
            return False
        now = datetime.now(timezone.utc)
        return any(
            ttl is None or (now - ts).total_seconds() < ttl
            for _, ts, ttl in self._vetoes[key]
        )

    def get_audit_trail(self) -> list[AuditEntry]:
        """Return the audit trail."""
        return list(self._audit_trail)


# ---------------------------------------------------------------------------
# F2T2EA Chain
# ---------------------------------------------------------------------------


class F2T2EAChain:
    """F2T2EA kill chain orchestrator."""

    def __init__(
        self,
        config: Optional[F2T2EAConfig] = None,
        governance: Optional[HumanGovernance] = None,
    ):
        self.config = config or F2T2EAConfig()
        self.governance = governance
        self._state = F2T2EAState()
        self._targets: dict[str, Target] = {}
        self._tracks: dict[str, Track] = {}
        self._engagements: list[EngagementResult] = []
        self._assessments: list[AssessmentResult] = []
        self._sensor_readings: list[SensorReading] = []
        self._latency_budget = LatencyBudget(threshold_ms=self.config.max_latency_ms)
        self._optimizer = LatencyOptimizer()

    @property
    def state(self) -> F2T2EAState:
        """Return the current state."""
        return self._state

    def advance_to(self, phase: F2T2EAPhase) -> None:
        """Advance to a specific phase (forward only)."""
        if self._state.is_terminal():
            raise F2T2EAError("Cannot advance a terminal chain")
        current_idx = list(F2T2EAPhase).index(self._state.current_phase)
        target_idx = list(F2T2EAPhase).index(phase)
        if target_idx < current_idx:
            raise F2T2EAError("Cannot revisit a completed phase")
        self._state.current_phase = phase
        self._state.history.append((datetime.now(timezone.utc), phase))

    def restart(self) -> None:
        """Restart the kill chain."""
        self._state = F2T2EAState()
        self._targets.clear()
        self._tracks.clear()
        self._engagements.clear()
        self._assessments.clear()
        self._sensor_readings.clear()

    def abort(self, reason: Optional[str] = None) -> None:
        """Abort the kill chain."""
        if reason is None and self._state.current_phase == F2T2EAPhase.FIND:
            raise F2T2EAError("Abort requires a reason when in initial state")
        self._state.status = KillChainStatus.ABORTED

    # --- Find Phase ---

    def submit_sensor_reading(self, reading: SensorReading) -> None:
        """Submit a sensor reading."""
        self._sensor_readings.append(reading)
        self._update_threat_level()

    def _update_threat_level(self) -> None:
        """Update threat level based on sensor readings."""
        if not self._sensor_readings:
            self._state.threat_level = ThreatLevel.LOW
            return
        max_confidence = max(r.confidence for r in self._sensor_readings)
        count = len(self._sensor_readings)
        if max_confidence >= 0.9 and count >= 5:
            self._state.threat_level = ThreatLevel.CRITICAL
        elif max_confidence >= 0.8:
            self._state.threat_level = ThreatLevel.HIGH
        elif max_confidence >= 0.5:
            self._state.threat_level = ThreatLevel.MEDIUM
        else:
            self._state.threat_level = ThreatLevel.LOW

    def confirm_find(self) -> None:
        """Confirm find and advance to fix."""
        if self._state.current_phase != F2T2EAPhase.FIND:
            raise F2T2EAError("Must be in FIND phase")
        self.advance_to(F2T2EAPhase.FIX)

    # --- Fix Phase ---

    def fix_target(
        self,
        location: Optional[tuple[float, float]],
        target_id: str,
        classification: str,
    ) -> Target:
        """Fix a target location."""
        if location is None:
            raise F2T2EAError("Target location is required")
        target = Target(
            target_id=target_id,
            location=location,
            threat_level=self._state.threat_level,
            classification=classification,
        )
        self._targets[target_id] = target
        return target

    def confirm_fix(self) -> None:
        """Confirm fix and advance to track."""
        if self._state.current_phase != F2T2EAPhase.FIX:
            raise F2T2EAError("Must be in FIX phase")
        self.advance_to(F2T2EAPhase.TRACK)

    # --- Track Phase ---

    def start_tracking(self, target_id: str, track_id: str) -> Track:
        """Start tracking a target."""
        track = Track(track_id=track_id, target_id=target_id)
        self._tracks[track_id] = track
        return track

    def update_track(self, track_id: str, location: tuple[float, float]) -> None:
        """Update a track's position."""
        if track_id not in self._tracks:
            raise F2T2EAError(f"Unknown track: {track_id}")
        self._tracks[track_id].latest_position = location
        self._tracks[track_id].last_update = datetime.now(timezone.utc)

    def get_track(self, track_id: str) -> Track:
        """Get a track by ID."""
        if track_id not in self._tracks:
            raise F2T2EAError(f"Unknown track: {track_id}")
        return self._tracks[track_id]

    def confirm_track(self) -> None:
        """Confirm track and advance to target."""
        if self._state.current_phase != F2T2EAPhase.TRACK:
            raise F2T2EAError("Must be in TRACK phase")
        self.advance_to(F2T2EAPhase.TARGET)

    # --- Target Phase ---

    def add_target(self, target: Target) -> None:
        """Add a target."""
        if target.target_id in self._targets:
            raise F2T2EAError(f"Duplicate target ID: {target.target_id}")
        self._targets[target.target_id] = target

    def prioritize_targets(self) -> list[Target]:
        """Return targets sorted by threat level (highest first)."""
        return sorted(self._targets.values(), key=lambda t: t.threat_level, reverse=True)

    def select_engagement(self, target_id: str) -> EngagementResult:
        """Select an engagement for a target."""
        if target_id not in self._targets:
            raise F2T2EAError(f"Unknown target: {target_id}")
        result = EngagementResult(
            target_id=target_id,
            shooter_id="",
            outcome=EngagementOutcome.SUCCESS,
        )
        return result

    def confirm_target(self) -> None:
        """Confirm target and advance to engage."""
        if self._state.current_phase != F2T2EAPhase.TARGET:
            raise F2T2EAError("Must be in TARGET phase")
        self.advance_to(F2T2EAPhase.ENGAGE)

    # --- Engage Phase ---

    def engage(
        self,
        target_id: str,
        shooter_id: str,
        outcome: EngagementOutcome,
    ) -> EngagementResult:
        """Execute an engagement."""
        # Check governance
        if self.governance is not None:
            if self.governance.is_vetoed(HumanDecision.ENGAGE, target_id):
                raise HumanGovernanceError(f"Engagement vetoed for target {target_id}")
            threat = self._targets.get(target_id)
            threat_level = threat.threat_level if threat else None
            if not self.governance.is_authorized(HumanDecision.ENGAGE, target_id, threat_level):
                raise HumanGovernanceError(f"Engagement not authorized for target {target_id}")

        # Target must exist
        if target_id not in self._targets:
            raise F2T2EAError(f"Unknown target: {target_id}")

        result = EngagementResult(
            target_id=target_id,
            shooter_id=shooter_id,
            outcome=outcome,
        )
        self._engagements.append(result)

        if outcome == EngagementOutcome.SUCCESS:
            self._targets[target_id].destroyed = True

        return result

    def confirm_engage(self) -> None:
        """Confirm engage and advance to assess."""
        if self._state.current_phase != F2T2EAPhase.ENGAGE:
            raise F2T2EAError("Must be in ENGAGE phase")
        self.advance_to(F2T2EAPhase.ASSESS)

    # --- Assess Phase ---

    def assess(
        self,
        target_id: str,
        effectiveness: float,
        collateral_damage: bool,
    ) -> AssessmentResult:
        """Perform battle damage assessment."""
        if not 0.0 <= effectiveness <= 1.0:
            raise ValueError("Effectiveness must be between 0 and 1")
        result = AssessmentResult(
            target_id=target_id,
            effectiveness=effectiveness,
            collateral_damage=collateral_damage,
            requires_re_engagement=effectiveness < 0.5,
        )
        self._assessments.append(result)
        return result

    def confirm_assess(self) -> None:
        """Confirm assess and complete the kill chain."""
        self._state.status = KillChainStatus.COMPLETE

    # --- Queries ---

    def get_target(self, target_id: str) -> Target:
        """Get a target by ID."""
        if target_id not in self._targets:
            raise F2T2EAError(f"Unknown target: {target_id}")
        return self._targets[target_id]
