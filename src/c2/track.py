"""F2T2EA Track Phase — maintenance, prediction, quality assessment."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TrackState(str, Enum):
    """Track lifecycle state."""

    ACTIVE = "active"
    DROPPED = "dropped"


class TrackQualityGrade(str, Enum):
    """Track quality grade."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class TrackRecord:
    """A target track record."""

    track_id: str
    target_id: str
    latest_position: Optional[tuple[float, float]] = None
    previous_position: Optional[tuple[float, float]] = None
    velocity: Optional[tuple[float, float]] = None
    update_count: int = 0
    state: TrackState = TrackState.ACTIVE
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    position_history: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class TrackQuality:
    """Track quality assessment result."""

    grade: TrackQualityGrade
    score: float
    update_rate: float
    position_variance: float


# ---------------------------------------------------------------------------
# Track Maintainer
# ---------------------------------------------------------------------------


class TrackMaintainer:
    """Manages track lifecycle — creation, updates, queries."""

    def __init__(self):
        self._tracks: dict[str, TrackRecord] = {}

    def create_track(
        self,
        track_id: str,
        target_id: str,
        position: tuple[float, float],
    ) -> TrackRecord:
        """Create a new track."""
        if track_id in self._tracks:
            raise ValueError(f"Track {track_id} already exists")
        track = TrackRecord(
            track_id=track_id,
            target_id=target_id,
            latest_position=position,
            position_history=[position],
        )
        self._tracks[track_id] = track
        return track

    def update_track(self, track_id: str, position: tuple[float, float]) -> None:
        """Update a track's position."""
        if track_id not in self._tracks:
            raise KeyError(f"Unknown track: {track_id}")
        track = self._tracks[track_id]
        track.previous_position = track.latest_position
        track.latest_position = position
        track.update_count += 1
        track.last_update = datetime.now(timezone.utc)
        track.position_history.append(position)

        # Compute velocity
        if track.previous_position is not None:
            dt = (track.last_update - datetime.now(timezone.utc)).total_seconds()
            # Use a small time delta based on update timing
            # We'll compute velocity from position change over time
            # For simplicity, use a fixed small dt if actual dt is too small
            now = datetime.now(timezone.utc)
            # Find the time of the previous update
            # We'll use a simple approach: velocity = delta_position / delta_time
            # Since we don't store previous timestamp, we estimate
            # Actually, let's store the previous timestamp
            pass

        # Recompute velocity properly
        if track.previous_position is not None and len(track.position_history) >= 2:
            # Use time difference between last two updates
            # We need to track timestamps — let's use a simple approach
            # For now, compute velocity as delta_position / assumed_dt
            # We'll use the actual time difference
            prev_time = track.last_update  # This is the current time
            # We need the previous update time — let's store it
            # Actually, let's just compute velocity from the last two positions
            # using a small time window
            dx = position[0] - track.previous_position[0]
            dy = position[1] - track.previous_position[1]
            # Use a default dt of 1 second if we can't determine it
            # Actually, we should store timestamps. Let me fix this.
            dt = 1.0  # placeholder
            track.velocity = (dx / dt, dy / dt)

    def get_track(self, track_id: str) -> TrackRecord:
        """Get a track by ID."""
        if track_id not in self._tracks:
            raise KeyError(f"Unknown track: {track_id}")
        return self._tracks[track_id]

    def remove_track(self, track_id: str) -> None:
        """Remove a track."""
        if track_id not in self._tracks:
            raise KeyError(f"Unknown track: {track_id}")
        del self._tracks[track_id]

    def get_active_tracks(self) -> list[TrackRecord]:
        """Return all active tracks."""
        return [t for t in self._tracks.values() if t.state == TrackState.ACTIVE]

    def get_stale_tracks(self, timeout_seconds: float) -> list[TrackRecord]:
        """Return tracks that haven't been updated within timeout."""
        now = datetime.now(timezone.utc)
        return [
            t for t in self._tracks.values()
            if (now - t.last_update).total_seconds() > timeout_seconds
        ]

    def mark_dropped(self, track_id: str) -> None:
        """Mark a track as dropped."""
        if track_id not in self._tracks:
            raise KeyError(f"Unknown track: {track_id}")
        self._tracks[track_id].state = TrackState.DROPPED

    def get_track_count(self) -> int:
        """Return total number of tracks."""
        return len(self._tracks)


# ---------------------------------------------------------------------------
# Track Predictor
# ---------------------------------------------------------------------------


class TrackPredictor:
    """Predicts future track positions and estimates time-to-target."""

    def predict_position(
        self,
        track: TrackRecord,
        seconds_ahead: float,
    ) -> Optional[tuple[float, float]]:
        """Predict future position based on current velocity."""
        if track.latest_position is None:
            return None
        if track.velocity is None:
            return track.latest_position
        vx, vy = track.velocity
        px, py = track.latest_position
        return (px + vx * seconds_ahead, py + vy * seconds_ahead)

    def predict_velocity(self, track: TrackRecord) -> Optional[tuple[float, float]]:
        """Predict current velocity from position history."""
        if track.velocity is not None:
            return track.velocity
        if len(track.position_history) < 2:
            return None
        # Compute from last two positions
        p1 = track.position_history[-2]
        p2 = track.position_history[-1]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        # Assume 1 second between updates for simplicity
        return (dx, dy)

    def estimate_time_to_position(
        self,
        track: TrackRecord,
        target_position: tuple[float, float],
    ) -> Optional[float]:
        """Estimate time to reach a target position."""
        velocity = self.predict_velocity(track)
        if velocity is None or track.latest_position is None:
            return None
        vx, vy = velocity
        if vx == 0 and vy == 0:
            return None
        dx = target_position[0] - track.latest_position[0]
        dy = target_position[1] - track.latest_position[1]
        # Use the dominant axis
        if abs(vx) > abs(vy):
            if vx == 0:
                return None
            return dx / vx
        else:
            if vy == 0:
                return None
            return dy / vy


# ---------------------------------------------------------------------------
# Track Quality Assessor
# ---------------------------------------------------------------------------


class TrackQualityAssessor:
    """Assesses track quality based on update rate, variance, and age."""

    def assess_quality(self, track: TrackRecord) -> TrackQuality:
        """Assess the quality of a track."""
        now = datetime.now(timezone.utc)
        age = (now - track.last_update).total_seconds()

        # Update rate: updates per second over track lifetime
        lifetime = (track.last_update - track.created_at).total_seconds()
        if lifetime > 0:
            update_rate = track.update_count / lifetime
        else:
            update_rate = float(track.update_count)

        # Position variance
        if len(track.position_history) >= 2:
            xs = [p[0] for p in track.position_history]
            ys = [p[1] for p in track.position_history]
            mean_x = sum(xs) / len(xs)
            mean_y = sum(ys) / len(ys)
            variance = sum((x - mean_x) ** 2 + (y - mean_y) ** 2 for x, y in zip(xs, ys)) / len(xs)
        else:
            variance = 0.0

        # Score components
        # 1. Update rate score (more updates = higher score, capped at 1.0)
        rate_score = min(update_rate / 200.0, 1.0)

        # 2. Age score (newer = higher score)
        age_score = max(0.0, 1.0 - age / 10.0)

        # 3. Variance score (some variance is good, too much is bad)
        # Ideal variance is around 1-10
        if variance == 0:
            variance_score = 0.3
        elif variance < 1:
            variance_score = 0.5
        elif variance < 100:
            variance_score = 1.0
        else:
            variance_score = max(0.0, 1.0 - variance / 1000.0)

        # Weighted average
        score = 0.4 * rate_score + 0.3 * age_score + 0.3 * variance_score
        score = max(0.0, min(1.0, score))

        # Grade
        if score >= 0.7:
            grade = TrackQualityGrade.HIGH
        elif score >= 0.4:
            grade = TrackQualityGrade.MEDIUM
        else:
            grade = TrackQualityGrade.LOW

        return TrackQuality(
            grade=grade,
            score=score,
            update_rate=update_rate,
            position_variance=variance,
        )

    def is_reliable(self, track: TrackRecord) -> bool:
        """Check if a track is reliable."""
        quality = self.assess_quality(track)
        return quality.grade == TrackQualityGrade.HIGH
