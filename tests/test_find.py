"""Tests for F2T2EA Find Phase — multi-source fusion, detection, contact reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from c2.find import (
    ContactReport,
    FusedContact,
    FindPhase,
    SensorReading,
    SensorSource,
    ThreatLevel,
)


def _reading(
    sensor_id: str,
    location: tuple[float, float],
    confidence: float = 0.8,
    classification: str = "aircraft",
    source: SensorSource = SensorSource.RADAR,
    timestamp: datetime | None = None,
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        source=source,
        timestamp=timestamp or datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
        location=location,
        confidence=confidence,
        classification=classification,
    )


# ---------------------------------------------------------------------------
# Sensor registration
# ---------------------------------------------------------------------------


class TestSensorRegistration:
    def test_register_sensor(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        assert "radar-1" in fp.sensors

    def test_register_multiple_sensors(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.register_sensor("acoustic-1", SensorSource.ACOUSTIC)
        assert len(fp.sensors) == 3

    def test_unknown_sensor_rejected(self):
        fp = FindPhase()
        with pytest.raises(ValueError, match="Unknown sensor"):
            fp.ingest(_reading("ghost-sensor", (0.0, 0.0)))

    def test_duplicate_sensor_registration_overwrites(self):
        fp = FindPhase()
        fp.register_sensor("s1", SensorSource.RADAR)
        fp.register_sensor("s1", SensorSource.SIGINT)
        assert fp.sensors["s1"] == SensorSource.SIGINT


# ---------------------------------------------------------------------------
# Single-source ingestion
# ---------------------------------------------------------------------------


class TestSingleSource:
    def test_single_reading_creates_contact(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (10.0, 20.0), confidence=0.9))
        contacts = fp.get_contacts()
        assert len(contacts) == 1

    def test_single_reading_contact_location(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (10.0, 20.0), confidence=0.9))
        contact = fp.get_contacts()[0]
        assert contact.location == pytest.approx((10.0, 20.0))

    def test_single_reading_contact_confidence(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (10.0, 20.0), confidence=0.75))
        contact = fp.get_contacts()[0]
        assert contact.confidence == pytest.approx(0.75)

    def test_empty_readings_no_contacts(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        assert fp.get_contacts() == []

    def test_contact_timestamp_from_reading(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        ts = datetime(2026, 10, 1, 12, 30, 0, tzinfo=timezone.utc)
        fp.ingest(_reading("radar-1", (1.0, 2.0), timestamp=ts))
        contact = fp.get_contacts()[0]
        assert contact.timestamp == ts


# ---------------------------------------------------------------------------
# Multi-source fusion
# ---------------------------------------------------------------------------


class TestMultiSourceFusion:
    def test_two_sources_fuse_into_single_contact(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (10.0, 20.0), confidence=0.8))
        fp.ingest(_reading("eo-1", (10.001, 20.001), confidence=0.7))
        contacts = fp.get_contacts()
        assert len(contacts) == 1

    def test_fusion_weighted_centroid(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("eo-1", (10.0, 10.0), confidence=0.1))
        contact = fp.get_contacts()[0]
        # Heavier weight on the 0.9-confidence reading
        assert contact.location[0] < 2.0
        assert contact.location[1] < 2.0

    def test_fusion_confidence_probabilistic_or(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.5))
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.5))
        contact = fp.get_contacts()[0]
        # 1 - (1-0.5)(1-0.5) = 0.75
        assert contact.confidence == pytest.approx(0.75)

    def test_fusion_confidence_monotonic_in_sources(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.5))
        c1 = fp.get_contacts()[0].confidence
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.5))
        c2 = fp.get_contacts()[0].confidence
        assert c2 > c1

    def test_fusion_requires_spatial_proximity(self):
        fp = FindPhase(spatial_threshold_km=5.0)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("eo-1", (100.0, 100.0), confidence=0.9))
        contacts = fp.get_contacts()
        assert len(contacts) == 2

    def test_fusion_requires_temporal_proximity(self):
        fp = FindPhase(temporal_window_seconds=60)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(
            _reading(
                "eo-1",
                (0.0, 0.0),
                confidence=0.9,
                timestamp=datetime(2026, 10, 1, 12, 5, 0, tzinfo=timezone.utc),
            )
        )
        contacts = fp.get_contacts()
        assert len(contacts) == 2

    def test_classification_majority_vote(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.register_sensor("acoustic-1", SensorSource.ACOUSTIC)
        fp.ingest(_reading("radar-1", (0.0, 0.0), classification="aircraft"))
        fp.ingest(_reading("eo-1", (0.0, 0.0), classification="aircraft"))
        fp.ingest(_reading("acoustic-1", (0.0, 0.0), classification="helicopter"))
        contact = fp.get_contacts()[0]
        assert contact.classification == "aircraft"

    def test_contributing_sensors_tracked(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0)))
        fp.ingest(_reading("eo-1", (0.0, 0.0)))
        contact = fp.get_contacts()[0]
        assert set(contact.contributing_sensors) == {"radar-1", "eo-1"}

    def test_sensor_source_diversity_bonus(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.6))
        c_single = fp.get_contacts()[0].confidence
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.6))
        c_fused = fp.get_contacts()[0].confidence
        assert c_fused > c_single

    def test_three_sources_fuse(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.register_sensor("sigint-1", SensorSource.SIGINT)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.6))
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.6))
        fp.ingest(_reading("sigint-1", (0.0, 0.0), confidence=0.6))
        contacts = fp.get_contacts()
        assert len(contacts) == 1
        # 1 - 0.4^3 = 0.936
        assert contacts[0].confidence == pytest.approx(0.936, rel=1e-3)


# ---------------------------------------------------------------------------
# Target detection
# ---------------------------------------------------------------------------


class TestTargetDetection:
    def test_detection_threshold_filters_low_confidence(self):
        fp = FindPhase(detection_threshold=0.7)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.5))
        assert fp.get_contacts() == []

    def test_detection_threshold_passes_high_confidence(self):
        fp = FindPhase(detection_threshold=0.7)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.8))
        assert len(fp.get_contacts()) == 1

    def test_fusion_can_push_above_threshold(self):
        fp = FindPhase(detection_threshold=0.8)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.6))
        assert fp.get_contacts() == []
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.6))
        assert len(fp.get_contacts()) == 1

    def test_multiple_distinct_targets_separate_contacts(self):
        fp = FindPhase(spatial_threshold_km=5.0)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("radar-1", (50.0, 50.0), confidence=0.9))
        contacts = fp.get_contacts()
        assert len(contacts) == 2

    def test_contact_count_matches_targets(self):
        fp = FindPhase(spatial_threshold_km=5.0)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("radar-1", (100.0, 100.0), confidence=0.9))
        fp.ingest(_reading("eo-1", (100.0, 100.0), confidence=0.9))
        assert len(fp.get_contacts()) == 2

    def test_contact_update_refines_location(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("eo-1", (1.0, 1.0), confidence=0.5))
        contact = fp.get_contacts()[0]
        # Weighted toward the higher-confidence reading
        assert contact.location[0] < 0.5
        assert contact.location[1] < 0.5

    def test_contact_id_stable_across_updates(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        cid = fp.get_contacts()[0].contact_id
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.7))
        assert fp.get_contacts()[0].contact_id == cid

    def test_threat_level_from_classification(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), classification="ballistic_missile"))
        contact = fp.get_contacts()[0]
        assert contact.threat_level == ThreatLevel.CRITICAL

    def test_threat_level_from_confidence(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.95))
        contact = fp.get_contacts()[0]
        assert contact.threat_level == ThreatLevel.HIGH

    def test_stale_readings_expire(self):
        fp = FindPhase(temporal_window_seconds=60, stale_threshold_seconds=60)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(
            _reading(
                "radar-1",
                (0.0, 0.0),
                confidence=0.9,
                timestamp=datetime(2026, 10, 1, 11, 0, 0, tzinfo=timezone.utc),
            )
        )
        fp.ingest(
            _reading(
                "radar-1",
                (0.0, 0.0),
                confidence=0.9,
                timestamp=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
        )
        contacts = fp.get_contacts()
        # Old reading expired; only the recent one forms a contact
        assert len(contacts) == 1


# ---------------------------------------------------------------------------
# Contact reporting
# ---------------------------------------------------------------------------


class TestContactReporting:
    def test_report_generated_for_detected_contact(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (10.0, 20.0), confidence=0.9))
        reports = fp.generate_reports()
        assert len(reports) == 1

    def test_report_contains_contact_info(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (10.0, 20.0), confidence=0.9))
        report = fp.generate_reports()[0]
        assert report.contact.location == pytest.approx((10.0, 20.0))
        assert report.contact.confidence == pytest.approx(0.9)

    def test_report_priority_high_threat(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), classification="ballistic_missile"))
        report = fp.generate_reports()[0]
        assert report.priority == ThreatLevel.CRITICAL

    def test_report_priority_low_threat(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.5, classification="bird"))
        report = fp.generate_reports()[0]
        assert report.priority == ThreatLevel.LOW

    def test_report_includes_recommended_action(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        report = fp.generate_reports()[0]
        assert report.recommended_action != ""

    def test_report_timestamp(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        report = fp.generate_reports()[0]
        assert isinstance(report.timestamp, datetime)

    def test_no_report_below_detection_threshold(self):
        fp = FindPhase(detection_threshold=0.8)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.5))
        assert fp.generate_reports() == []

    def test_report_includes_contributing_sensors(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.register_sensor("eo-1", SensorSource.EO_IR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.8))
        fp.ingest(_reading("eo-1", (0.0, 0.0), confidence=0.7))
        report = fp.generate_reports()[0]
        assert set(report.contact.contributing_sensors) == {"radar-1", "eo-1"}

    def test_multiple_reports_for_multiple_contacts(self):
        fp = FindPhase(spatial_threshold_km=5.0)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("radar-1", (100.0, 100.0), confidence=0.9))
        reports = fp.generate_reports()
        assert len(reports) == 2

    def test_report_id_unique(self):
        fp = FindPhase(spatial_threshold_km=5.0)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.ingest(_reading("radar-1", (100.0, 100.0), confidence=0.9))
        reports = fp.generate_reports()
        ids = [r.report_id for r in reports]
        assert len(ids) == len(set(ids))

    def test_reports_sorted_by_priority(self):
        fp = FindPhase(spatial_threshold_km=5.0)
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.95))
        fp.ingest(
            _reading("radar-1", (100.0, 100.0), confidence=0.5, classification="bird")
        )
        reports = fp.generate_reports()
        assert reports[0].priority >= reports[1].priority


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_confidence_bounds_enforced(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        with pytest.raises(ValueError):
            fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=1.5))
        with pytest.raises(ValueError):
            fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=-0.1))

    def test_fusion_confidence_never_exceeds_one(self):
        fp = FindPhase()
        for i in range(10):
            fp.register_sensor(f"sensor-{i}", SensorSource.RADAR)
            fp.ingest(_reading(f"sensor-{i}", (0.0, 0.0), confidence=0.99))
        contact = fp.get_contacts()[0]
        assert contact.confidence <= 1.0

    def test_get_contact_by_id(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (5.0, 5.0), confidence=0.9))
        contact = fp.get_contacts()[0]
        assert fp.get_contact(contact.contact_id) is not None

    def test_get_contact_unknown_id_raises(self):
        fp = FindPhase()
        with pytest.raises(ValueError, match="Unknown contact"):
            fp.get_contact("nonexistent")

    def test_clear_contacts(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.clear()
        assert fp.get_contacts() == []

    def test_clear_resets_reports(self):
        fp = FindPhase()
        fp.register_sensor("radar-1", SensorSource.RADAR)
        fp.ingest(_reading("radar-1", (0.0, 0.0), confidence=0.9))
        fp.generate_reports()
        fp.clear()
        assert fp.generate_reports() == []
