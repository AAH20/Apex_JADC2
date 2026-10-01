"""Coalition Federation Protocol.

NATO FMN interoperability, multi-national data sharing, and classification
level management for joint all-domain command and control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CoalitionError(Exception):
    """Base exception for coalition federation operations."""


class SecurityViolation(CoalitionError):
    """Raised when a security policy is violated."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ClassificationLevel(int, Enum):
    """Classification levels ordered by sensitivity."""

    UNCLASSIFIED = 0
    RESTRICTED = 1
    CONFIDENTIAL = 2
    SECRET = 3
    TOP_SECRET = 4

    @classmethod
    def from_string(cls, name: str) -> ClassificationLevel:
        """Parse a classification level from string."""
        normalized = name.upper().replace(" ", "_").replace("-", "_")
        try:
            return cls[normalized]
        except KeyError:
            raise ValueError(f"Unknown classification level: {name}") from None


class FMNProfile(str, Enum):
    """NATO FMN (Federated Mission Network) spiral profiles."""

    FMN_SPIRAL_1 = "FMN_SPIRAL_1"
    FMN_SPIRAL_2 = "FMN_SPIRAL_2"
    FMN_SPIRAL_3 = "FMN_SPIRAL_3"
    FMN_SPIRAL_4 = "FMN_SPIRAL_4"
    FMN_SPIRAL_5 = "FMN_SPIRAL_5"


# ---------------------------------------------------------------------------
# Releaseability Marking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReleaseabilityMarking:
    """REL TO marking indicating which nations/groups data is releasable to."""

    releasable_to: frozenset[str] = field(default_factory=frozenset)

    def __init__(self, releasable_to: Optional[list[str] | set[str] | frozenset[str]] = None):
        if releasable_to is None:
            object.__setattr__(self, "releasable_to", frozenset())
        elif isinstance(releasable_to, frozenset):
            object.__setattr__(self, "releasable_to", releasable_to)
        else:
            object.__setattr__(self, "releasable_to", frozenset(releasable_to))

    def is_releasable_to(self, entity: str) -> bool:
        """Check if data is releasable to the given entity."""
        return entity in self.releasable_to

    @classmethod
    def nato_default(cls) -> ReleaseabilityMarking:
        """Create a default NATO releaseability marking."""
        return cls(["NATO"])

    def to_string(self) -> str:
        """Return the REL TO string representation."""
        if not self.releasable_to:
            return "NO REL"
        return "REL TO " + ", ".join(sorted(self.releasable_to))


# ---------------------------------------------------------------------------
# Classification Marking
# ---------------------------------------------------------------------------


@dataclass
class ClassificationMarking:
    """Full classification marking for a data item."""

    level: ClassificationLevel
    releaseability: ReleaseabilityMarking
    compartments: set[str] = field(default_factory=set)
    sub_compartments: set[str] = field(default_factory=set)

    def to_string(self) -> str:
        """Return the full classification string."""
        parts = [self.level.name.replace("_", " ")]
        if self.releaseability.releasable_to:
            parts.append(self.releaseability.to_string())
        if self.compartments:
            parts.append("//" + "/".join(sorted(self.compartments)))
        if self.sub_compartments:
            parts.append("//" + "/".join(sorted(self.sub_compartments)))
        return " ".join(parts) if len(parts) == 1 else parts[0] + " " + " ".join(parts[1:])

    @classmethod
    def parse(cls, marking_str: str) -> ClassificationMarking:
        """Parse a classification marking string."""
        parts = marking_str.split("//")
        level_part = parts[0].strip()
        level = ClassificationLevel.from_string(level_part)

        releaseability = ReleaseabilityMarking()
        compartments: set[str] = set()
        sub_compartments: set[str] = set()

        for part in parts[1:]:
            part = part.strip()
            if part.startswith("REL TO"):
                rel_str = part[6:].strip()
                entities = {e.strip() for e in rel_str.split(",")}
                releaseability = ReleaseabilityMarking(entities)
            elif part:
                # Treat as compartment
                compartments.add(part)

        return cls(
            level=level,
            releaseability=releaseability,
            compartments=compartments,
            sub_compartments=sub_compartments,
        )

    def dominates(self, other: ClassificationMarking) -> bool:
        """Check if this marking dominates (can access) another marking."""
        if self.level < other.level:
            return False
        if not other.releaseability.releasable_to.issubset(self.releaseability.releasable_to):
            return False
        if not other.compartments.issubset(self.compartments):
            return False
        return True


# ---------------------------------------------------------------------------
# Coalition Partner
# ---------------------------------------------------------------------------


@dataclass
class CoalitionPartner:
    """A coalition partner nation/organization."""

    partner_id: str
    name: str
    clearance_level: ClassificationLevel
    releaseability: set[str] = field(default_factory=set)
    compartments: set[str] = field(default_factory=set)
    fmn_profiles: set[FMNProfile] = field(default_factory=set)

    def can_access(self, marking: ClassificationMarking) -> bool:
        """Check if this partner can access data with the given marking."""
        if self.clearance_level < marking.level:
            return False
        if not marking.releaseability.releasable_to.issubset(self.releaseability):
            return False
        if not marking.compartments.issubset(self.compartments):
            return False
        return True


# ---------------------------------------------------------------------------
# Data Item
# ---------------------------------------------------------------------------


@dataclass
class DataItem:
    """A data item shared within the coalition."""

    item_id: str
    content: Any
    marking: ClassificationMarking
    source_partner: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.marking is None:
            raise ValueError("DataItem requires a classification marking")


# ---------------------------------------------------------------------------
# FMN Message
# ---------------------------------------------------------------------------


@dataclass
class FMNMessage:
    """A message in the NATO FMN format."""

    message_id: str
    sender_id: str
    recipient_ids: list[str]
    profile: FMNProfile
    payload: dict[str, Any]
    marking: ClassificationMarking
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_ids": list(self.recipient_ids),
            "profile": self.profile.value,
            "payload": self.payload,
            "marking": self.marking.to_string(),
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
        }


# ---------------------------------------------------------------------------
# Cross-Domain Guard
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    """An audit trail entry."""

    action: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)


class CrossDomainGuard:
    """Guards transfers between classification domains."""

    def __init__(self):
        self._audit_trail: list[AuditEntry] = []

    def check_transfer(
        self,
        source_marking: ClassificationMarking,
        target_level: ClassificationLevel,
    ) -> bool:
        """Check if a transfer from source marking to target level is allowed."""
        # Transfer is allowed if target level is same or lower (downgrade)
        if target_level <= source_marking.level:
            self._audit_trail.append(AuditEntry(
                action="allowed",
                timestamp=datetime.now(timezone.utc),
                details={
                    "source_level": source_marking.level.name,
                    "target_level": target_level.name,
                },
            ))
            return True
        else:
            self._audit_trail.append(AuditEntry(
                action="blocked",
                timestamp=datetime.now(timezone.utc),
                details={
                    "source_level": source_marking.level.name,
                    "target_level": target_level.name,
                },
            ))
            return False

    def get_audit_trail(self) -> list[AuditEntry]:
        """Return the audit trail."""
        return list(self._audit_trail)


# ---------------------------------------------------------------------------
# Federation Gateway
# ---------------------------------------------------------------------------


class FederationGateway:
    """Central gateway for coalition federation operations."""

    def __init__(self):
        self._partners: dict[str, CoalitionPartner] = {}
        self._shared_data: dict[str, list[DataItem]] = {}
        self._messages: dict[str, list[FMNMessage]] = {}
        self._audit_trail: list[AuditEntry] = []
        self._guard = CrossDomainGuard()

    def register_partner(self, partner: CoalitionPartner) -> None:
        """Register a coalition partner."""
        if partner.partner_id in self._partners:
            raise ValueError(f"Partner already registered: {partner.partner_id}")
        self._partners[partner.partner_id] = partner
        self._shared_data[partner.partner_id] = []
        self._messages[partner.partner_id] = []

    def get_partner(self, partner_id: str) -> CoalitionPartner:
        """Get a registered partner by ID."""
        if partner_id not in self._partners:
            raise ValueError(f"Unknown partner: {partner_id}")
        return self._partners[partner_id]

    def share_data(
        self,
        item: DataItem,
        source_partner_id: str,
        recipient_ids: list[str],
    ) -> None:
        """Share a data item with specified recipients."""
        # Verify source partner exists
        if source_partner_id not in self._partners:
            raise ValueError(f"Unknown source partner: {source_partner_id}")

        # Check each recipient can access
        for recipient_id in recipient_ids:
            if recipient_id not in self._partners:
                raise ValueError(f"Unknown recipient: {recipient_id}")
            recipient = self._partners[recipient_id]
            if not recipient.can_access(item.marking):
                raise SecurityViolation(
                    f"Partner {recipient_id} cannot access {item.item_id} "
                    f"with marking {item.marking.to_string()}"
                )

        # Share the data
        for recipient_id in recipient_ids:
            self._shared_data[recipient_id].append(item)

        # Also keep at source
        if source_partner_id not in recipient_ids:
            self._shared_data[source_partner_id].append(item)

        self._audit_trail.append(AuditEntry(
            action="share",
            timestamp=datetime.now(timezone.utc),
            details={
                "item_id": item.item_id,
                "source": source_partner_id,
                "recipients": list(recipient_ids),
            },
        ))

    def get_shared_data(self, partner_id: str) -> list[DataItem]:
        """Get all data shared with a partner."""
        if partner_id not in self._shared_data:
            raise ValueError(f"Unknown partner: {partner_id}")
        return list(self._shared_data[partner_id])

    def send_fmn_message(self, message: FMNMessage) -> None:
        """Send an FMN message to recipients."""
        # Verify sender exists
        if message.sender_id not in self._partners:
            raise ValueError(f"Unknown sender: {message.sender_id}")

        # Check each recipient can access
        for recipient_id in message.recipient_ids:
            if recipient_id not in self._partners:
                raise ValueError(f"Unknown recipient: {recipient_id}")
            recipient = self._partners[recipient_id]
            if not recipient.can_access(message.marking):
                raise SecurityViolation(
                    f"Partner {recipient_id} cannot access message {message.message_id} "
                    f"with marking {message.marking.to_string()}"
                )

        # Deliver message
        for recipient_id in message.recipient_ids:
            self._messages[recipient_id].append(message)

        self._audit_trail.append(AuditEntry(
            action="fmn_message",
            timestamp=datetime.now(timezone.utc),
            details={
                "message_id": message.message_id,
                "sender": message.sender_id,
                "recipients": list(message.recipient_ids),
                "profile": message.profile.value,
            },
        ))

    def get_messages_for_partner(self, partner_id: str) -> list[FMNMessage]:
        """Get all messages for a partner."""
        if partner_id not in self._messages:
            raise ValueError(f"Unknown partner: {partner_id}")
        return list(self._messages[partner_id])

    def get_audit_trail(self) -> list[AuditEntry]:
        """Return the audit trail."""
        return list(self._audit_trail)
