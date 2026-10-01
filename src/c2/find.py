"""F2T2EA Find Phase — multi-source sensor fusion, target detection, contact reporting."""

from __future__ import annotations

import math
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SensorSource(str, Enum):
    """Types of sensor sources."""

    RADAR = "radar"
    EO_IR = "eo_ir"
    ACOUSTIC = "acoustic"
    SIGINT = "sigint"
    HUMINT = "humint"
    SATELLITE = "satellite"


class ThreatLevel(int, Enum):
    """Threat severity levels."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


# Classification → threat mapping
_CLASSIFICATION_THREAT: dict[str, ThreatLevel] = {
    "ballistic_missile": ThreatLevel.CRITICAL,
    "cruise_missile": ThreatLevel.CRITICAL,
    "fighter_aircraft": ThreatLevel.HIGH,
    "bomber": ThreatLevel.HIGH,
    "helicopter": ThreatLevel.MEDIUM,
    "uav": ThreatLevel.MEDIUM,
    "surface_vehicle": ThreatLevel.LOW,
    "personnel": ThreatLevel.LOW,
    "bird": ThreatLevel.LOW,
    "unknown": ThreatLevel.LOW,
}


@dataclass
class SensorReading:
    """A single sensor detection reading."""

    sensor_id: str
    source: SensorSource
    timestamp: datetime
    location: tuple[float, float]
    confidence: float
    classification: str = "unknown"

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")


@dataclass
class FusedContact:
    """A fused contact from one or more sensor readings."""

    contact_id: str
    location: tuple[float, float]
    confidence: float
    classification: str
    threat_level: ThreatLevel
    contributing_sensors: set[str] = field(default_factory=set)
    sources: set[SensorSource] = field(default_factory=set)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reading_count: int = 0


@dataclass
class ContactReport:
    """A contact report for downstream C2 consumption."""

    report_id: str
    contact: FusedContact
    priority: ThreatLevel
    recommended_action: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Compute haversine distance in km between two (lat, lon) points."""
    R = 6371.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _classify_threat(classification: str, confidence: float) -> ThreatLevel:
    """Determine threat level from classification and confidence."""
    base = _CLASSIFICATION_THREAT.get(classification, ThreatLevel.LOW)
    if base == ThreatLevel.LOW:
        if confidence >= 0.95:
            return ThreatLevel.HIGH
        if confidence >= 0.9:
            return ThreatLevel.MEDIUM
    return base


def _recommended_action(threat: ThreatLevel, classification: str) -> str:
    """Generate a recommended action string."""
    if threat == ThreatLevel.CRITICAL:
        return f"IMMEDIATE ALERT: {classification} detected — escalate to engagement authority"
    if threat == ThreatLevel.HIGH:
        return f"PRIORITY: Track and prepare engagement for {classification}"
    if threat == ThreatLevel.MEDIUM:
        return f"MONITOR: Continue tracking {classification}"
    return f"LOG: Record {classification} for situational awareness"


class FindPhase:
    """F2T2EA Find Phase implementation.

    Ingests sensor readings from multiple sources, fuses them into
    contacts using spatial-temporal proximity, detects targets above
    a confidence threshold, and generates contact reports.
    """

    def __init__(
        self,
        spatial_threshold_km: float = 10.0,
        temporal_window_seconds: float = 300.0,
        detection_threshold: float = 0.5,
        stale_threshold_seconds: float = 3600.0,
    ):
        self.spatial_threshold_km = spatial_threshold_km
        self.temporal_window_seconds = temporal_window_seconds
        self.detection_threshold = detection_threshold
        self.stale_threshold_seconds = stale_threshold_seconds
        self._sensors: dict[str, SensorSource] = {}
        self._readings: list[SensorReading] = []
        self._contacts: dict[str, FusedContact] = {}
        self._reports: list[ContactReport] = []

    @property
    def sensors(self) -> dict[str, SensorSource]:
        """Return registered sensors."""
        return dict(self._sensors)

    def register_sensor(self, sensor_id: str, source: SensorSource) -> None:
        """Register a sensor for ingestion."""
        self._sensors[sensor_id] = source

    def ingest(self, reading: SensorReading) -> None:
        """Ingest a sensor reading and update fused contacts."""
        if reading.sensor_id not in self._sensors:
            raise ValueError(f"Unknown sensor: {reading.sensor_id}")
        self._readings.append(reading)
        self._update_contacts(reading)

    def _update_contacts(self, reading: SensorReading) -> None:
        """Update fused contacts with a new reading."""
        best_contact: Optional[FusedContact] = None
        best_dist = float("inf")

        for contact in self._contacts.values():
            dist = _haversine_km(reading.location, contact.location)
            if dist <= self.spatial_threshold_km and dist < best_dist:
                time_diff = abs(
                    (reading.timestamp - contact.timestamp).total_seconds()
                )
                if time_diff <= self.temporal_window_seconds:
                    best_contact = contact
                    best_dist = dist

        if best_contact is not None:
            self._merge_reading_into_contact(best_contact, reading)
        else:
            self._create_contact(reading)

    def _create_contact(self, reading: SensorReading) -> FusedContact:
        """Create a new fused contact from a reading."""
        source = self._sensors[reading.sensor_id]
        contact = FusedContact(
            contact_id=str(uuid.uuid4()),
            location=reading.location,
            confidence=reading.confidence,
            classification=reading.classification,
            threat_level=_classify_threat(reading.classification, reading.confidence),
            contributing_sensors={reading.sensor_id},
            sources={source},
            timestamp=reading.timestamp,
            reading_count=1,
        )
        self._contacts[contact.contact_id] = contact
        return contact

    def _merge_reading_into_contact(
        self, contact: FusedContact, reading: SensorReading
    ) -> None:
        """Merge a reading into an existing contact."""
        source = self._sensors[reading.sensor_id]

        # Weighted centroid update
        old_weight = contact.confidence
        new_weight = reading.confidence
        total_weight = old_weight + new_weight
        if total_weight > 0:
            w1 = old_weight / total_weight
            w2 = new_weight / total_weight
            contact.location = (
                w1 * contact.location[0] + w2 * reading.location[0],
                w1 * contact.location[1] + w2 * reading.location[1],
            )

        # Probabilistic OR fusion for confidence
        contact.confidence = 1.0 - (1.0 - contact.confidence) * (1.0 - reading.confidence)

        # Track sources and sensors
        contact.sources.add(source)
        contact.contributing_sensors.add(reading.sensor_id)
        contact.reading_count += 1

        # Classification: majority vote from all contributing readings
        reading_classifications = [
            r.classification
            for r in self._readings
            if r.sensor_id in contact.contributing_sensors
        ]
        if reading_classifications:
            counter = Counter(reading_classifications)
            contact.classification = counter.most_common(1)[0][0]

        # Update threat level
        contact.threat_level = _classify_threat(
            contact.classification, contact.confidence
        )

        # Update timestamp to most recent
        if reading.timestamp > contact.timestamp:
            contact.timestamp = reading.timestamp

    def get_contacts(self) -> list[FusedContact]:
        """Return all contacts above the detection threshold, excluding stale ones."""
        if not self._readings:
            return []
        latest_ts = max(r.timestamp for r in self._readings)
        return [
            c for c in self._contacts.values()
            if c.confidence >= self.detection_threshold
            and (latest_ts - c.timestamp).total_seconds() <= self.stale_threshold_seconds
        ]

    def get_contact(self, contact_id: str) -> FusedContact:
        """Get a contact by ID."""
        if contact_id not in self._contacts:
            raise ValueError(f"Unknown contact: {contact_id}")
        return self._contacts[contact_id]

    def generate_reports(self) -> list[ContactReport]:
        """Generate contact reports for all detected contacts."""
        self._reports = []
        contacts = self.get_contacts()
        contacts.sort(key=lambda c: (c.threat_level, c.confidence), reverse=True)
        for contact in contacts:
            report = ContactReport(
                report_id=str(uuid.uuid4()),
                contact=contact,
                priority=contact.threat_level,
                recommended_action=_recommended_action(
                    contact.threat_level, contact.classification
                ),
            )
            self._reports.append(report)
        return list(self._reports)

    def clear(self) -> None:
        """Clear all contacts and reports."""
        self._contacts.clear()
        self._reports.clear()
