"""Tests for F2T2EA Track Phase — maintenance, prediction, quality assessment."""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

import pytest

from c2.track import (
    TrackMaintainer,
    TrackPredictor,
    TrackQualityAssessor,
    TrackRecord,
    TrackState,
    TrackQualityGrade,
    TrackQuality,
)


# ===========================================================================
# TrackMaintainer Tests
# ===========================================================================


class TestTrackMaintainer:
    """Track lifecycle management tests."""

    def test_create_track(self):
        maintainer = TrackMaintainer()
        track = maintainer.create_track("T001", "target-1", (100.0, 200.0))
        assert track.track_id == "T001"
        assert track.target_id == "target-1"
        assert track.latest_position == (100.0, 200.0)
        assert track.state == TrackState.ACTIVE

    def test_create_track_duplicate_id_raises(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        with pytest.raises(ValueError, match="already exists"):
            maintainer.create_track("T001", "target-2", (300.0, 400.0))

    def test_update_track_position(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.update_track("T001", (150.0, 250.0))
        track = maintainer.get_track("T001")
        assert track.latest_position == (150.0, 250.0)
        assert track.previous_position == (100.0, 200.0)

    def test_update_track_increments_count(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.update_track("T001", (150.0, 250.0))
        maintainer.update_track("T001", (200.0, 300.0))
        track = maintainer.get_track("T001")
        assert track.update_count == 2

    def test_update_track_computes_velocity(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        time.sleep(0.01)
        maintainer.update_track("T001", (10.0, 0.0))
        track = maintainer.get_track("T001")
        assert track.velocity is not None
        assert track.velocity[0] > 0
        assert abs(track.velocity[1]) < 0.001

    def test_get_track_unknown_raises(self):
        maintainer = TrackMaintainer()
        with pytest.raises(KeyError):
            maintainer.get_track("NONEXISTENT")

    def test_remove_track(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.remove_track("T001")
        assert maintainer.get_track_count() == 0

    def test_remove_track_unknown_raises(self):
        maintainer = TrackMaintainer()
        with pytest.raises(KeyError):
            maintainer.remove_track("NONEXISTENT")

    def test_get_active_tracks(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.create_track("T002", "target-2", (300.0, 400.0))
        maintainer.mark_dropped("T002")
        active = maintainer.get_active_tracks()
        assert len(active) == 1
        assert active[0].track_id == "T001"

    def test_get_stale_tracks(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.create_track("T002", "target-2", (300.0, 400.0))
        # Manually set T001's last_update to be old
        old_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        maintainer._tracks["T001"].last_update = old_time
        stale = maintainer.get_stale_tracks(timeout_seconds=50)
        assert len(stale) == 1
        assert stale[0].track_id == "T001"

    def test_mark_dropped(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.mark_dropped("T001")
        track = maintainer.get_track("T001")
        assert track.state == TrackState.DROPPED

    def test_get_track_count(self):
        maintainer = TrackMaintainer()
        assert maintainer.get_track_count() == 0
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        maintainer.create_track("T002", "target-2", (300.0, 400.0))
        assert maintainer.get_track_count() == 2

    def test_update_track_unknown_raises(self):
        maintainer = TrackMaintainer()
        with pytest.raises(KeyError):
            maintainer.update_track("NONEXISTENT", (100.0, 200.0))

    def test_create_track_stores_position_history(self):
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (100.0, 200.0))
        track = maintainer.get_track("T001")
        assert (100.0, 200.0) in track.position_history


# ===========================================================================
# TrackPredictor Tests
# ===========================================================================


class TestTrackPredictor:
    """Track prediction tests."""

    def test_predict_position_linear(self):
        predictor = TrackPredictor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        time.sleep(0.01)
        maintainer.update_track("T001", (10.0, 5.0))
        track = maintainer.get_track("T001")
        future_pos = predictor.predict_position(track, seconds_ahead=2.0)
        assert future_pos is not None
        # Should be roughly (0 + vx*2, 0 + vy*2)
        assert future_pos[0] > 10.0
        assert future_pos[1] > 5.0

    def test_predict_position_no_history(self):
        predictor = TrackPredictor()
        track = TrackRecord(track_id="T001", target_id="target-1", latest_position=(100.0, 200.0))
        future_pos = predictor.predict_position(track, seconds_ahead=5.0)
        # No velocity data, should return current position
        assert future_pos == (100.0, 200.0)

    def test_predict_velocity(self):
        predictor = TrackPredictor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        time.sleep(0.01)
        maintainer.update_track("T001", (10.0, 0.0))
        track = maintainer.get_track("T001")
        velocity = predictor.predict_velocity(track)
        assert velocity is not None
        assert velocity[0] > 0
        assert abs(velocity[1]) < 0.001

    def test_predict_velocity_no_history(self):
        predictor = TrackPredictor()
        track = TrackRecord(track_id="T001", target_id="target-1", latest_position=(100.0, 200.0))
        velocity = predictor.predict_velocity(track)
        assert velocity is None

    def test_estimate_time_to_position(self):
        predictor = TrackPredictor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        time.sleep(0.01)
        maintainer.update_track("T001", (10.0, 0.0))
        track = maintainer.get_track("T001")
        # Target at (50, 0), velocity ~10 m/s in x
        eta = predictor.estimate_time_to_position(track, (50.0, 0.0))
        assert eta is not None
        assert eta > 0

    def test_estimate_time_to_position_no_velocity(self):
        predictor = TrackPredictor()
        track = TrackRecord(track_id="T001", target_id="target-1", latest_position=(100.0, 200.0))
        eta = predictor.estimate_time_to_position(track, (150.0, 250.0))
        assert eta is None


# ===========================================================================
# TrackQualityAssessor Tests
# ===========================================================================


class TestTrackQualityAssessor:
    """Track quality assessment tests."""

    def test_assess_quality_high(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        # Multiple rapid updates
        for i in range(10):
            time.sleep(0.005)
            maintainer.update_track("T001", (float(i), 0.0))
        track = maintainer.get_track("T001")
        quality = assessor.assess_quality(track)
        assert quality.grade == TrackQualityGrade.HIGH
        assert quality.score > 0.7

    def test_assess_quality_medium(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        # A few updates with some gap
        for i in range(3):
            time.sleep(0.02)
            maintainer.update_track("T001", (float(i), 0.0))
        track = maintainer.get_track("T001")
        quality = assessor.assess_quality(track)
        assert quality.grade == TrackQualityGrade.MEDIUM

    def test_assess_quality_low(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        # Only one update, long ago
        old_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        maintainer._tracks["T001"].last_update = old_time
        track = maintainer.get_track("T001")
        quality = assessor.assess_quality(track)
        assert quality.grade == TrackQualityGrade.LOW

    def test_quality_score_range(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        track = maintainer.get_track("T001")
        quality = assessor.assess_quality(track)
        assert 0.0 <= quality.score <= 1.0

    def test_is_reliable_true(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        for i in range(10):
            time.sleep(0.005)
            maintainer.update_track("T001", (float(i), 0.0))
        track = maintainer.get_track("T001")
        assert assessor.is_reliable(track) is True

    def test_is_reliable_false(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        old_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        maintainer._tracks["T001"].last_update = old_time
        track = maintainer.get_track("T001")
        assert assessor.is_reliable(track) is False

    def test_quality_includes_update_rate(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        for i in range(5):
            time.sleep(0.01)
            maintainer.update_track("T001", (float(i), 0.0))
        track = maintainer.get_track("T001")
        quality = assessor.assess_quality(track)
        assert quality.update_rate > 0

    def test_quality_includes_position_variance(self):
        assessor = TrackQualityAssessor()
        maintainer = TrackMaintainer()
        maintainer.create_track("T001", "target-1", (0.0, 0.0))
        for i in range(5):
            time.sleep(0.01)
            maintainer.update_track("T001", (float(i), 0.0))
        track = maintainer.get_track("T001")
        quality = assessor.assess_quality(track)
        assert quality.position_variance >= 0
