"""F2T2EA Fix phase: location refinement, track initiation, position estimation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.c2.f2t2ea import SensorReading, Track


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class RefinedLocation:
    """A refined target location with uncertainty."""

    location: tuple[float, float]
    uncertainty: float
    num_readings: int


@dataclass
class PositionEstimate:
    """A position estimate with velocity and confidence."""

    position: tuple[float, float]
    velocity: tuple[float, float]
    confidence: float


# ---------------------------------------------------------------------------
# Location Refinement
# ---------------------------------------------------------------------------


class LocationRefiner:
    """Refines target location from multiple sensor readings."""

    def refine(
        self,
        readings: list[SensorReading],
        max_distance: Optional[float] = None,
    ) -> RefinedLocation:
        """Refine location from sensor readings using confidence-weighted average."""
        if not readings:
            raise ValueError("at least one reading")

        filtered = readings
        if max_distance is not None:
            filtered = self.filter_outliers(readings, max_distance)
            if not filtered:
                filtered = readings

        total_weight = sum(r.confidence for r in filtered)
        if total_weight == 0:
            total_weight = 1.0

        lat = sum(r.location[0] * r.confidence for r in filtered) / total_weight
        lon = sum(r.location[1] * r.confidence for r in filtered) / total_weight

        uncertainty = self.compute_uncertainty(filtered)

        return RefinedLocation(
            location=(lat, lon),
            uncertainty=uncertainty,
            num_readings=len(filtered),
        )

    def filter_outliers(
        self,
        readings: list[SensorReading],
        max_distance: float,
    ) -> list[SensorReading]:
        """Remove readings that are too far from the median location."""
        if not readings:
            return []

        lats = sorted(r.location[0] for r in readings)
        lons = sorted(r.location[1] for r in readings)
        mid = len(readings) // 2
        median_lat = lats[mid]
        median_lon = lons[mid]

        return [
            r for r in readings
            if self._distance(r.location, (median_lat, median_lon)) <= max_distance
        ]

    def compute_uncertainty(self, readings: list[SensorReading]) -> float:
        """Compute uncertainty as standard deviation of readings from centroid."""
        if len(readings) <= 1:
            return 0.0

        centroid_lat = sum(r.location[0] for r in readings) / len(readings)
        centroid_lon = sum(r.location[1] for r in readings) / len(readings)

        variance = sum(
            self._distance(r.location, (centroid_lat, centroid_lon)) ** 2
            for r in readings
        ) / len(readings)

        return math.sqrt(variance)

    @staticmethod
    def _distance(
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


# ---------------------------------------------------------------------------
# Track Initiation
# ---------------------------------------------------------------------------


class TrackInitiator:
    """Manages track initiation and lifecycle."""

    def __init__(self) -> None:
        self._tracks: dict[str, Track] = {}
        self._counter: int = 0

    def initiate(
        self,
        target_id: str,
        initial_position: tuple[float, float],
        classification: str = "",
    ) -> Track:
        """Initiate a new track for a target."""
        if target_id in self._tracks:
            raise ValueError(f"Track already exists for target: {target_id}")

        self._counter += 1
        track_id = f"track-{self._counter}"
        track = Track(
            track_id=track_id,
            target_id=target_id,
            latest_position=initial_position,
            last_update=datetime.now(timezone.utc),
        )
        self._tracks[target_id] = track
        return track

    def update(self, track_id: str, position: tuple[float, float]) -> None:
        """Update a track's position."""
        track = self._find_by_track_id(track_id)
        if track is None:
            raise ValueError(f"Unknown track: {track_id}")
        track.latest_position = position
        track.last_update = datetime.now(timezone.utc)

    def get_track(self, track_id: str) -> Track:
        """Get a track by its track_id."""
        track = self._find_by_track_id(track_id)
        if track is None:
            raise ValueError(f"Unknown track: {track_id}")
        return track

    def terminate(self, track_id: str) -> None:
        """Terminate a track."""
        track = self._find_by_track_id(track_id)
        if track is None:
            raise ValueError(f"Unknown track: {track_id}")
        del self._tracks[track.target_id]

    def _find_by_track_id(self, track_id: str) -> Optional[Track]:
        """Find a track by its track_id."""
        for track in self._tracks.values():
            if track.track_id == track_id:
                return track
        return None


# ---------------------------------------------------------------------------
# Position Estimation
# ---------------------------------------------------------------------------


class PositionEstimator:
    """Estimates position and velocity from sensor readings."""

    def estimate(self, readings: list[SensorReading]) -> PositionEstimate:
        """Estimate position and velocity from readings."""
        if not readings:
            raise ValueError("at least one reading")

        sorted_readings = sorted(readings, key=lambda r: r.timestamp)

        # Position: latest reading's position
        latest = sorted_readings[-1]
        position = latest.location

        velocity = self.compute_velocity(sorted_readings)
        confidence = sum(r.confidence for r in sorted_readings) / len(sorted_readings)

        return PositionEstimate(
            position=position,
            velocity=velocity,
            confidence=confidence,
        )

    def compute_velocity(
        self,
        readings: list[SensorReading],
    ) -> tuple[float, float]:
        """Compute velocity from first and last readings."""
        if len(readings) < 2:
            return (0.0, 0.0)

        sorted_readings = sorted(readings, key=lambda r: r.timestamp)
        first = sorted_readings[0]
        last = sorted_readings[-1]

        dt = (last.timestamp - first.timestamp).total_seconds()
        if dt <= 0:
            return (0.0, 0.0)

        vx = (last.location[0] - first.location[0]) / dt
        vy = (last.location[1] - first.location[1]) / dt
        return (vx, vy)

    def predict(
        self,
        estimate: PositionEstimate,
        seconds_ahead: float,
    ) -> tuple[float, float]:
        """Predict future position based on current estimate."""
        return (
            estimate.position[0] + estimate.velocity[0] * seconds_ahead,
            estimate.position[1] + estimate.velocity[1] * seconds_ahead,
        )
