"""Tests for F2T2EA Fix phase: location refinement, track initiation, position estimation."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from src.c2.f2t2ea import SensorReading, ThreatLevel
from src.c2.fix import (
    LocationRefiner,
    PositionEstimate,
    PositionEstimator,
    RefinedLocation,
    TrackInitiator,
)


def _reading(
    sensor_id: str,
    lat: float,
    lon: float,
    confidence: float,
    classification: str = "vehicle",
    timestamp: datetime | None = None,
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        location=(lat, lon),
        confidence=confidence,
        classification=classification,
    )


# ---------------------------------------------------------------------------
# LocationRefiner
# ---------------------------------------------------------------------------


class TestLocationRefiner:
    def test_refine_single_reading(self):
        r = LocationRefiner()
        reading = _reading("s1", 10.0, 20.0, 0.9)
        result = r.refine([reading])
        assert result.location == (10.0, 20.0)
        assert result.num_readings == 1

    def test_refine_multiple_readings_weighted(self):
        r = LocationRefiner()
        readings = [
            _reading("s1", 0.0, 0.0, 0.5),
            _reading("s2", 10.0, 10.0, 1.0),
        ]
        result = r.refine(readings)
        # Weighted: (0*0.5 + 10*1.0) / 1.5 = 6.667
        assert result.location[0] == pytest.approx(20.0 / 3.0, abs=0.01)
        assert result.location[1] == pytest.approx(20.0 / 3.0, abs=0.01)
        assert result.num_readings == 2

    def test_refine_empty_readings_raises(self):
        r = LocationRefiner()
        with pytest.raises(ValueError, match="at least one reading"):
            r.refine([])

    def test_refine_returns_refined_location_type(self):
        r = LocationRefiner()
        result = r.refine([_reading("s1", 1.0, 2.0, 0.8)])
        assert isinstance(result, RefinedLocation)
        assert result.uncertainty >= 0.0

    def test_filter_outliers_removes_distant(self):
        r = LocationRefiner()
        readings = [
            _reading("s1", 0.0, 0.0, 0.9),
            _reading("s2", 0.1, 0.1, 0.9),
            _reading("s3", 100.0, 100.0, 0.9),
        ]
        filtered = r.filter_outliers(readings, max_distance=10.0)
        assert len(filtered) == 2
        assert all(rd.sensor_id != "s3" for rd in filtered)

    def test_filter_outliers_keeps_all_when_close(self):
        r = LocationRefiner()
        readings = [
            _reading("s1", 0.0, 0.0, 0.9),
            _reading("s2", 0.1, 0.1, 0.9),
            _reading("s3", 0.2, 0.2, 0.9),
        ]
        filtered = r.filter_outliers(readings, max_distance=10.0)
        assert len(filtered) == 3

    def test_filter_outliers_empty_returns_empty(self):
        r = LocationRefiner()
        assert r.filter_outliers([], max_distance=10.0) == []

    def test_compute_uncertainty_zero_for_identical(self):
        r = LocationRefiner()
        readings = [
            _reading("s1", 5.0, 5.0, 0.9),
            _reading("s2", 5.0, 5.0, 0.9),
        ]
        uncertainty = r.compute_uncertainty(readings)
        assert uncertainty == pytest.approx(0.0, abs=1e-9)

    def test_compute_uncertainty_positive_for_spread(self):
        r = LocationRefiner()
        readings = [
            _reading("s1", 0.0, 0.0, 0.9),
            _reading("s2", 10.0, 10.0, 0.9),
        ]
        uncertainty = r.compute_uncertainty(readings)
        assert uncertainty > 0.0

    def test_refine_with_outlier_filtering(self):
        r = LocationRefiner()
        readings = [
            _reading("s1", 0.0, 0.0, 0.9),
            _reading("s2", 0.1, 0.1, 0.9),
            _reading("s3", 50.0, 50.0, 0.1),
        ]
        result = r.refine(readings, max_distance=15.0)
        assert result.num_readings == 2
        assert result.location[0] < 1.0
        assert result.location[1] < 1.0


# ---------------------------------------------------------------------------
# TrackInitiator
# ---------------------------------------------------------------------------


class TestTrackInitiator:
    def test_initiate_creates_track(self):
        ti = TrackInitiator()
        track = ti.initiate("t1", (10.0, 20.0), "vehicle")
        assert track.target_id == "t1"
        assert track.latest_position == (10.0, 20.0)
        assert track.track_id is not None

    def test_initiate_duplicate_raises(self):
        ti = TrackInitiator()
        ti.initiate("t1", (10.0, 20.0), "vehicle")
        with pytest.raises(ValueError, match="already exists"):
            ti.initiate("t1", (30.0, 40.0), "vehicle")

    def test_update_track_position(self):
        ti = TrackInitiator()
        track = ti.initiate("t1", (10.0, 20.0), "vehicle")
        ti.update(track.track_id, (15.0, 25.0))
        updated = ti.get_track(track.track_id)
        assert updated.latest_position == (15.0, 25.0)

    def test_update_unknown_track_raises(self):
        ti = TrackInitiator()
        with pytest.raises(ValueError, match="Unknown track"):
            ti.update("nonexistent", (1.0, 2.0))

    def test_get_track(self):
        ti = TrackInitiator()
        track = ti.initiate("t1", (10.0, 20.0), "vehicle")
        fetched = ti.get_track(track.track_id)
        assert fetched.target_id == "t1"

    def test_get_unknown_track_raises(self):
        ti = TrackInitiator()
        with pytest.raises(ValueError, match="Unknown track"):
            ti.get_track("nonexistent")

    def test_terminate_track(self):
        ti = TrackInitiator()
        track = ti.initiate("t1", (10.0, 20.0), "vehicle")
        ti.terminate(track.track_id)
        with pytest.raises(ValueError, match="Unknown track"):
            ti.get_track(track.track_id)

    def test_terminate_unknown_track_raises(self):
        ti = TrackInitiator()
        with pytest.raises(ValueError, match="Unknown track"):
            ti.terminate("nonexistent")

    def test_multiple_tracks_independent(self):
        ti = TrackInitiator()
        t1 = ti.initiate("t1", (0.0, 0.0), "vehicle")
        t2 = ti.initiate("t2", (100.0, 100.0), "aircraft")
        assert ti.get_track(t1.track_id).latest_position == (0.0, 0.0)
        assert ti.get_track(t2.track_id).latest_position == (100.0, 100.0)


# ---------------------------------------------------------------------------
# PositionEstimator
# ---------------------------------------------------------------------------


class TestPositionEstimator:
    def test_estimate_single_reading(self):
        pe = PositionEstimator()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        reading = _reading("s1", 10.0, 20.0, 0.9, timestamp=ts)
        result = pe.estimate([reading])
        assert result.position == (10.0, 20.0)
        assert result.velocity == (0.0, 0.0)

    def test_estimate_multiple_readings(self):
        pe = PositionEstimator()
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=10)
        readings = [
            _reading("s1", 0.0, 0.0, 0.9, timestamp=ts1),
            _reading("s2", 10.0, 20.0, 0.9, timestamp=ts2),
        ]
        result = pe.estimate(readings)
        assert result.position[0] == pytest.approx(10.0, abs=0.01)
        assert result.position[1] == pytest.approx(20.0, abs=0.01)
        assert result.velocity[0] == pytest.approx(1.0, abs=0.01)
        assert result.velocity[1] == pytest.approx(2.0, abs=0.01)

    def test_estimate_empty_raises(self):
        pe = PositionEstimator()
        with pytest.raises(ValueError, match="at least one reading"):
            pe.estimate([])

    def test_estimate_returns_position_estimate_type(self):
        pe = PositionEstimator()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = pe.estimate([_reading("s1", 1.0, 2.0, 0.8, timestamp=ts)])
        assert isinstance(result, PositionEstimate)
        assert result.confidence > 0.0

    def test_compute_velocity_stationary(self):
        pe = PositionEstimator()
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=10)
        readings = [
            _reading("s1", 5.0, 5.0, 0.9, timestamp=ts1),
            _reading("s2", 5.0, 5.0, 0.9, timestamp=ts2),
        ]
        velocity = pe.compute_velocity(readings)
        assert velocity == (0.0, 0.0)

    def test_compute_velocity_moving(self):
        pe = PositionEstimator()
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=5)
        readings = [
            _reading("s1", 0.0, 0.0, 0.9, timestamp=ts1),
            _reading("s2", 10.0, 5.0, 0.9, timestamp=ts2),
        ]
        velocity = pe.compute_velocity(readings)
        assert velocity[0] == pytest.approx(2.0, abs=0.01)
        assert velocity[1] == pytest.approx(1.0, abs=0.01)

    def test_predict_future_position(self):
        pe = PositionEstimator()
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=10)
        readings = [
            _reading("s1", 0.0, 0.0, 0.9, timestamp=ts1),
            _reading("s2", 10.0, 20.0, 0.9, timestamp=ts2),
        ]
        estimate = pe.estimate(readings)
        predicted = pe.predict(estimate, seconds_ahead=5.0)
        assert predicted[0] == pytest.approx(15.0, abs=0.01)
        assert predicted[1] == pytest.approx(30.0, abs=0.01)

    def test_predict_zero_time(self):
        pe = PositionEstimator()
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=10)
        readings = [
            _reading("s1", 0.0, 0.0, 0.9, timestamp=ts1),
            _reading("s2", 10.0, 20.0, 0.9, timestamp=ts2),
        ]
        estimate = pe.estimate(readings)
        predicted = pe.predict(estimate, seconds_ahead=0.0)
        assert predicted[0] == pytest.approx(10.0, abs=0.01)
        assert predicted[1] == pytest.approx(20.0, abs=0.01)

    def test_estimate_confidence_weighted(self):
        pe = PositionEstimator()
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=10)
        readings = [
            _reading("s1", 0.0, 0.0, 0.5, timestamp=ts1),
            _reading("s2", 10.0, 20.0, 1.0, timestamp=ts2),
        ]
        result = pe.estimate(readings)
        assert result.confidence == pytest.approx(0.75, abs=0.01)
