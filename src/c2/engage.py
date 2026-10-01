"""F2T2EA Engage Phase — Weapon-Target Assignment, Authorization, Deconfliction.

Implements the Engage phase of the F2T2EA kill chain with:
- Weapon-Target Assignment (WTA) algorithm
- Engagement authorization with human governance
- Deconfliction rules (temporal, spatial)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EngagePhaseError(Exception):
    """Base exception for Engage phase operations."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WeaponType(str, Enum):
    """Types of weapons available for engagement."""

    MISSILE = "missile"
    GUN = "gun"
    LASER = "laser"
    ELECTRONIC_WARFARE = "electronic_warfare"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class WeaponTargetAssignment:
    """Assignment of a weapon to a target."""

    weapon_id: str
    target_id: str
    shooter_id: str
    weapon_type: WeaponType
    priority: int = 0
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WeaponTargetAssignment):
            return NotImplemented
        return (
            self.weapon_id == other.weapon_id
            and self.target_id == other.target_id
            and self.shooter_id == other.shooter_id
            and self.weapon_type == other.weapon_type
            and self.priority == other.priority
        )

    def __hash__(self) -> int:
        return hash((self.weapon_id, self.target_id, self.shooter_id, self.weapon_type, self.priority))


@dataclass
class AssignmentResult:
    """Result of a weapon-target assignment operation."""

    success: bool
    assignment: Optional[WeaponTargetAssignment] = None
    reason: Optional[str] = None

    def __str__(self) -> str:
        if self.success and self.assignment is not None:
            return f"Assignment(success={self.success}, weapon={self.assignment.weapon_id}, target={self.assignment.target_id})"
        return f"Assignment(success={self.success}, reason={self.reason})"


@dataclass
class AutoAssignResult:
    """Result of an auto-assignment operation."""

    assignments: list[WeaponTargetAssignment] = field(default_factory=list)
    unassigned_targets: list[str] = field(default_factory=list)


@dataclass
class EngagementAuthorization:
    """Authorization for engaging a target."""

    target_id: str
    authorized: bool
    authorizer_id: str
    authorization_type: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if the authorization has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class AuthorizationResult:
    """Result of an authorization check."""

    target_id: str
    authorized: bool
    authorization_type: Optional[str] = None
    reason: Optional[str] = None

    def __str__(self) -> str:
        return f"Authorization(target={self.target_id}, authorized={self.authorized})"


@dataclass
class DeconflictionRule:
    """A deconfliction rule."""

    rule_id: str
    rule_type: str
    parameters: dict = field(default_factory=dict)


@dataclass
class DeconflictionResult:
    """Result of a deconfliction check."""

    is_clear: bool
    target_id: str
    blocking_rule: Optional[str] = None
    reason: Optional[str] = None

    def __str__(self) -> str:
        return f"Deconfliction(target={self.target_id}, clear={self.is_clear})"


@dataclass
class _WeaponInfo:
    """Internal weapon registration info."""

    weapon_id: str
    weapon_type: WeaponType
    capabilities: set[str]
    max_range: float = float("inf")
    assigned_to: Optional[str] = None


@dataclass
class _ShooterInfo:
    """Internal shooter registration info."""

    shooter_id: str
    capabilities: set[str]
    max_weapons: int = 1
    assigned_count: int = 0


@dataclass
class _EngagementRecord:
    """Record of a past engagement for deconfliction."""

    target_id: str
    shooter_id: str
    weapon_id: str
    timestamp: float
    location: Optional[tuple[float, float]] = None


# ---------------------------------------------------------------------------
# Weapon-Target Assigner
# ---------------------------------------------------------------------------


class WeaponTargetAssigner:
    """Assigns weapons to targets using constraint-based matching."""

    def __init__(self):
        self.weapons: dict[str, _WeaponInfo] = {}
        self.shooters: dict[str, _ShooterInfo] = {}
        self.targets: set[str] = set()
        self.active_assignments: dict[str, WeaponTargetAssignment] = {}

    def register_weapon(
        self,
        weapon_id: str,
        weapon_type: WeaponType,
        capabilities: set[str],
        max_range: float = float("inf"),
    ) -> None:
        """Register a weapon for assignment."""
        if weapon_id in self.weapons:
            raise EngagePhaseError(f"Weapon already registered: {weapon_id}")
        self.weapons[weapon_id] = _WeaponInfo(
            weapon_id=weapon_id,
            weapon_type=weapon_type,
            capabilities=capabilities,
            max_range=max_range,
        )

    def register_shooter(
        self,
        shooter_id: str,
        capabilities: set[str],
        max_weapons: int = 1,
    ) -> None:
        """Register a shooter platform."""
        if shooter_id in self.shooters:
            raise EngagePhaseError(f"Shooter already registered: {shooter_id}")
        self.shooters[shooter_id] = _ShooterInfo(
            shooter_id=shooter_id,
            capabilities=capabilities,
            max_weapons=max_weapons,
        )

    def register_target(self, target_id: str) -> None:
        """Register a target for assignment."""
        self.targets.add(target_id)

    def assign(
        self,
        target_id: str,
        weapon_id: str,
        shooter_id: str,
        priority: int = 0,
    ) -> AssignmentResult:
        """Assign a specific weapon to a target via a shooter."""
        if target_id not in self.targets:
            raise EngagePhaseError(f"Unknown target: {target_id}")
        if weapon_id not in self.weapons:
            raise EngagePhaseError(f"Unknown weapon: {weapon_id}")
        if shooter_id not in self.shooters:
            raise EngagePhaseError(f"Unknown shooter: {shooter_id}")

        weapon = self.weapons[weapon_id]
        shooter = self.shooters[shooter_id]

        # Check weapon availability
        if weapon.assigned_to is not None:
            raise EngagePhaseError(f"Weapon {weapon_id} already assigned to {weapon.assigned_to}")

        # Check shooter capacity
        if shooter.assigned_count >= shooter.max_weapons:
            raise EngagePhaseError(f"Shooter {shooter_id} at capacity ({shooter.max_weapons})")

        # Check capability match — empty weapon capabilities means no restriction
        if weapon.capabilities and not weapon.capabilities.issubset(shooter.capabilities):
            return AssignmentResult(
                success=False,
                reason=f"Shooter {shooter_id} lacks required capabilities",
            )

        # Create assignment
        assignment = WeaponTargetAssignment(
            weapon_id=weapon_id,
            target_id=target_id,
            shooter_id=shooter_id,
            weapon_type=weapon.weapon_type,
            priority=priority,
        )

        weapon.assigned_to = target_id
        shooter.assigned_count += 1
        self.active_assignments[weapon_id] = assignment

        return AssignmentResult(success=True, assignment=assignment)

    def auto_assign(
        self,
        target_ids: list[str],
        threat_levels: Optional[dict[str, int]] = None,
        target_ranges: Optional[dict[str, float]] = None,
    ) -> AutoAssignResult:
        """Automatically assign weapons to targets based on priority and constraints."""
        result = AutoAssignResult()
        threat_levels = threat_levels or {}
        target_ranges = target_ranges or {}

        # Auto-register targets
        for tid in target_ids:
            self.register_target(tid)

        # Sort targets by threat level (highest first)
        sorted_targets = sorted(
            target_ids,
            key=lambda t: threat_levels.get(t, 0),
            reverse=True,
        )

        # Get available weapons sorted by range (longest first for flexibility)
        available_weapons = [
            w for w in self.weapons.values() if w.assigned_to is None
        ]
        available_weapons.sort(key=lambda w: w.max_range, reverse=True)

        for target_id in sorted_targets:
            target_range = target_ranges.get(target_id, 0.0)
            assigned = False

            for weapon in available_weapons:
                if weapon.assigned_to is not None:
                    continue
                if weapon.max_range < target_range:
                    continue

                # Find a suitable shooter
                for shooter in self.shooters.values():
                    if shooter.assigned_count >= shooter.max_weapons:
                        continue
                    if weapon.weapon_type.value not in shooter.capabilities:
                        continue

                    assign_result = self.assign(target_id, weapon.weapon_id, shooter.shooter_id)
                    if assign_result.success and assign_result.assignment is not None:
                        result.assignments.append(assign_result.assignment)
                        assigned = True
                        break

                if assigned:
                    break

            if not assigned:
                result.unassigned_targets.append(target_id)

        return result

    def unassign(self, weapon_id: str) -> None:
        """Remove a weapon assignment."""
        if weapon_id not in self.active_assignments:
            raise EngagePhaseError(f"No active assignment for weapon: {weapon_id}")

        assignment = self.active_assignments.pop(weapon_id)
        self.weapons[weapon_id].assigned_to = None
        self.shooters[assignment.shooter_id].assigned_count -= 1

    def get_assignments_for_target(self, target_id: str) -> list[WeaponTargetAssignment]:
        """Get all assignments for a specific target."""
        return [a for a in self.active_assignments.values() if a.target_id == target_id]

    def get_assignments_for_shooter(self, shooter_id: str) -> list[WeaponTargetAssignment]:
        """Get all assignments for a specific shooter."""
        return [a for a in self.active_assignments.values() if a.shooter_id == shooter_id]

    def clear_all(self) -> None:
        """Clear all assignments."""
        self.active_assignments.clear()
        for weapon in self.weapons.values():
            weapon.assigned_to = None
        for shooter in self.shooters.values():
            shooter.assigned_count = 0


# ---------------------------------------------------------------------------
# Engagement Authorizer
# ---------------------------------------------------------------------------


class EngagementAuthorizer:
    """Manages engagement authorization with human governance."""

    def __init__(self, require_dual_for_critical: bool = False):
        self.require_dual_for_critical = require_dual_for_critical
        self._authorizations: dict[str, list[EngagementAuthorization]] = {}

    def authorize(
        self,
        target_id: str,
        authorizer_id: str,
        authorization_type: str = "explicit",
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Authorize engagement of a target."""
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        auth = EngagementAuthorization(
            target_id=target_id,
            authorized=True,
            authorizer_id=authorizer_id,
            authorization_type=authorization_type,
            expires_at=expires_at,
        )

        if target_id not in self._authorizations:
            self._authorizations[target_id] = []
        self._authorizations[target_id].append(auth)

    def revoke(self, target_id: str, authorizer_id: str) -> None:
        """Revoke an authorization."""
        if target_id not in self._authorizations:
            raise EngagePhaseError(f"No authorizations for target: {target_id}")
        self._authorizations[target_id] = [
            a for a in self._authorizations[target_id]
            if a.authorizer_id != authorizer_id
        ]

    def is_authorized(self, target_id: str) -> bool:
        """Check if a target is authorized for engagement."""
        result = self.check_authorization(target_id)
        return result.authorized

    def check_authorization(
        self,
        target_id: str,
        threat_level: Optional[int] = None,
    ) -> AuthorizationResult:
        """Check authorization status for a target."""
        if target_id not in self._authorizations:
            return AuthorizationResult(
                target_id=target_id,
                authorized=False,
                reason="No authorization found",
            )

        now = datetime.now(timezone.utc)
        valid_auths = [
            a for a in self._authorizations[target_id]
            if not a.is_expired()
        ]

        if not valid_auths:
            return AuthorizationResult(
                target_id=target_id,
                authorized=False,
                reason="All authorizations expired",
            )

        # Check dual authorization for critical threats
        if self.require_dual_for_critical and threat_level is not None and threat_level >= 3:
            if len(valid_auths) < 2:
                return AuthorizationResult(
                    target_id=target_id,
                    authorized=False,
                    reason="Dual authorization required for critical threat",
                )

        latest = max(valid_auths, key=lambda a: a.created_at)
        return AuthorizationResult(
            target_id=target_id,
            authorized=True,
            authorization_type=latest.authorization_type,
        )

    def get_authorization_info(self, target_id: str) -> Optional[EngagementAuthorization]:
        """Get the latest valid authorization for a target."""
        if target_id not in self._authorizations:
            return None
        valid = [a for a in self._authorizations[target_id] if not a.is_expired()]
        if not valid:
            return None
        return max(valid, key=lambda a: a.created_at)

    def clear(self) -> None:
        """Clear all authorizations."""
        self._authorizations.clear()


# ---------------------------------------------------------------------------
# Deconfliction Engine
# ---------------------------------------------------------------------------


class DeconflictionEngine:
    """Checks and enforces deconfliction rules for engagements."""

    def __init__(self):
        self.rules: dict[str, DeconflictionRule] = {}
        self.engagement_history: list[_EngagementRecord] = []

    def add_rule(self, rule: DeconflictionRule) -> None:
        """Add a deconfliction rule."""
        self.rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> None:
        """Remove a deconfliction rule."""
        if rule_id not in self.rules:
            raise EngagePhaseError(f"Unknown rule: {rule_id}")
        del self.rules[rule_id]

    def check_deconfliction(
        self,
        target_id: str,
        shooter_id: str,
        weapon_id: str,
        location: Optional[tuple[float, float]] = None,
    ) -> DeconflictionResult:
        """Check if an engagement passes all deconfliction rules."""
        now = time.time()

        for rule in self.rules.values():
            if rule.rule_type == "temporal":
                min_interval = rule.parameters.get("min_interval_seconds", 0)
                for record in self.engagement_history:
                    if (record.target_id == target_id
                            and record.shooter_id == shooter_id
                            and record.weapon_id == weapon_id):
                        elapsed = now - record.timestamp
                        if elapsed < min_interval:
                            return DeconflictionResult(
                                is_clear=False,
                                target_id=target_id,
                                blocking_rule=rule.rule_id,
                                reason=f"Temporal deconfliction: {elapsed:.1f}s < {min_interval}s",
                            )

            elif rule.rule_type == "spatial":
                min_distance = rule.parameters.get("min_distance_meters", 0)
                if location is not None:
                    for record in self.engagement_history:
                        if record.location is not None:
                            dist = self._haversine_distance(location, record.location)
                            if dist < min_distance:
                                return DeconflictionResult(
                                    is_clear=False,
                                    target_id=target_id,
                                    blocking_rule=rule.rule_id,
                                    reason=f"Spatial deconfliction: {dist:.0f}m < {min_distance}m",
                                )

        return DeconflictionResult(is_clear=True, target_id=target_id)

    def record_engagement(
        self,
        target_id: str,
        shooter_id: str,
        weapon_id: str,
        location: Optional[tuple[float, float]] = None,
    ) -> None:
        """Record an engagement for deconfliction tracking."""
        self.engagement_history.append(_EngagementRecord(
            target_id=target_id,
            shooter_id=shooter_id,
            weapon_id=weapon_id,
            timestamp=time.time(),
            location=location,
        ))

    def clear_history(self) -> None:
        """Clear engagement history."""
        self.engagement_history.clear()

    @staticmethod
    def _haversine_distance(
        loc1: tuple[float, float],
        loc2: tuple[float, float],
    ) -> float:
        """Calculate haversine distance between two lat/lon points in meters."""
        R = 6371000  # Earth radius in meters
        lat1, lon1 = math.radians(loc1[0]), math.radians(loc1[1])
        lat2, lon2 = math.radians(loc2[0]), math.radians(loc2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c


# ---------------------------------------------------------------------------
# Engage Phase Facade
# ---------------------------------------------------------------------------


class EngagePhase:
    """F2T2EA Engage Phase facade combining WTA, authorization, and deconfliction."""

    def __init__(self, require_dual_for_critical: bool = False):
        self.assigner = WeaponTargetAssigner()
        self.authorizer = EngagementAuthorizer(require_dual_for_critical=require_dual_for_critical)
        self.deconfliction = DeconflictionEngine()

    def clear_all(self) -> None:
        """Clear all state."""
        self.assigner.clear_all()
        self.authorizer.clear()
        self.deconfliction.clear_history()
