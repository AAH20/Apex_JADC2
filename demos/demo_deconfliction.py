#!/usr/bin/env python3
"""
demo_deconfliction.py — Airspace Deconfliction Demonstration
============================================================

Demonstrates airspace deconfliction for Apex_JADC2 using sample track data.
Detects potential conflicts between aircraft/missiles operating in the
same airspace and suggests resolution maneuvers.

Conflict types detected:
  - PROXIMITY: Two tracks within minimum separation distance
  - ALTITUDE:  Tracks at similar altitudes on converging courses
  - CROSSING:  Tracks whose paths will cross within a time window

Usage:
    python3 demo_deconfliction.py
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum


class ConflictType(Enum):
    """Types of airspace conflicts."""
    PROXIMITY = "Proximity"
    ALTITUDE = "Altitude"
    CROSSING = "Path Crossing"


class ResolutionType(Enum):
    """Types of resolution maneuvers."""
    CLIMB = "Climb"
    DESCEND = "Descend"
    TURN_LEFT = "Turn Left"
    TURN_RIGHT = "Turn Right"
    SPEED_UP = "Speed Up"
    SLOW_DOWN = "Slow Down"
    NO_ACTION = "No Action Required"


@dataclass
class AirTrack:
    """Represents an aircraft or missile track in airspace."""
    track_id: str
    track_type: str  # AIR, CM, UAV, HELO
    position: tuple  # (x_nm, y_nm, alt_ft) — nautical miles, feet
    velocity: tuple  # (heading_deg, speed_kts)
    callsign: str = ""
    flight_plan: str = ""


@dataclass
class Conflict:
    """Represents a detected conflict between two tracks."""
    track_a: str
    track_b: str
    conflict_type: ConflictType
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    time_to_conflict_min: float
    distance_at_conflict_nm: float
    description: str


@dataclass
class Resolution:
    """Represents a suggested resolution for a conflict."""
    conflict: Conflict
    primary_track: str
    resolution_type: ResolutionType
    instruction: str
    new_heading: Optional[float] = None
    new_altitude: Optional[int] = None
    new_speed: Optional[int] = None


def haversine_distance(pos1: tuple, pos2: tuple) -> float:
    """
    Calculate distance between two positions in nautical miles.
    Simplified flat-earth approximation for short distances.
    """
    x1, y1, _ = pos1
    x2, y2, _ = pos2
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def compute_closest_point_of_approach(
    pos1: tuple, vel1: tuple, pos2: tuple, vel2: tuple
) -> Tuple[float, float]:
    """
    Compute Closest Point of Approach (CPA) between two tracks.
    
    Returns:
        (time_to_cpa_minutes, distance_at_cpa_nm)
    """
    x1, y1, _ = pos1
    hdg1, spd1 = vel1
    x2, y2, _ = pos2
    hdg2, spd2 = vel2
    
    # Convert to velocity vectors (nm per minute)
    v1x = spd1 * math.sin(math.radians(hdg1)) / 60.0
    v1y = spd1 * math.cos(math.radians(hdg1)) / 60.0
    v2x = spd2 * math.sin(math.radians(hdg2)) / 60.0
    v2y = spd2 * math.cos(math.radians(hdg2)) / 60.0
    
    # Relative velocity
    vrx = v1x - v2x
    vry = v1y - v2y
    
    # Relative position
    rx = x1 - x2
    ry = y1 - y2
    
    # Time to CPA (minutes)
    v_rel_sq = vrx ** 2 + vry ** 2
    if v_rel_sq < 0.001:
        return (999.0, haversine_distance(pos1, pos2))
    
    t_cpa = -(rx * vrx + ry * vry) / v_rel_sq
    
    if t_cpa < 0:
        # CPA is in the past, tracks diverging
        return (0.0, haversine_distance(pos1, pos2))
    
    # Distance at CPA
    cpa_x1 = x1 + v1x * t_cpa
    cpa_y1 = y1 + v1y * t_cpa
    cpa_x2 = x2 + v2x * t_cpa
    cpa_y2 = y2 + v2y * t_cpa
    
    d_cpa = math.sqrt((cpa_x2 - cpa_x1) ** 2 + (cpa_y2 - cpa_y1) ** 2)
    
    return (round(t_cpa, 2), round(d_cpa, 2))


def detect_conflicts(tracks: List[AirTrack]) -> List[Conflict]:
    """
    Detect conflicts between all pairs of tracks.
    
    Minimum separation standards:
    - Lateral: 5 NM
    - Vertical: 1000 ft
    - Time: 15 minutes
    """
    conflicts = []
    
    # Separation standards
    MIN_LATERAL_NM = 5.0
    MIN_VERTICAL_FT = 1000.0
    TIME_HORIZON_MIN = 15.0
    
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            t1 = tracks[i]
            t2 = tracks[j]
            
            # Compute CPA
            t_cpa, d_cpa = compute_closest_point_of_approach(
                t1.position, t1.velocity, t2.position, t2.velocity
            )
            
            # Check altitude separation
            alt_diff = abs(t1.position[2] - t2.position[2])
            
            # Determine if conflict exists
            if t_cpa <= TIME_HORIZON_MIN and d_cpa < MIN_LATERAL_NM:
                # Determine severity
                if d_cpa < 2.0 and alt_diff < 500:
                    severity = "CRITICAL"
                elif d_cpa < 3.0 and alt_diff < 1000:
                    severity = "HIGH"
                elif d_cpa < 5.0 and alt_diff < 1000:
                    severity = "MEDIUM"
                else:
                    severity = "LOW"
                
                # Determine conflict type
                if alt_diff < MIN_VERTICAL_FT and d_cpa < MIN_LATERAL_NM:
                    conflict_type = ConflictType.ALTITUDE
                    desc = (f"Tracks {t1.track_id} and {t2.track_id} at similar altitudes "
                           f"({t1.position[2]}ft vs {t2.position[2]}ft) with lateral closure")
                elif d_cpa < MIN_LATERAL_NM:
                    conflict_type = ConflictType.PROXIMITY
                    desc = (f"Tracks {t1.track_id} and {t2.track_id} will be {d_cpa}NM apart "
                           f"in {t_cpa} minutes")
                else:
                    conflict_type = ConflictType.CROSSING
                    desc = (f"Tracks {t1.track_id} and {t2.track_id} on crossing courses, "
                           f"CPA {d_cpa}NM in {t_cpa}min")
                
                conflicts.append(Conflict(
                    track_a=t1.track_id,
                    track_b=t2.track_id,
                    conflict_type=conflict_type,
                    severity=severity,
                    time_to_conflict_min=t_cpa,
                    distance_at_conflict_nm=d_cpa,
                    description=desc
                ))
    
    return conflicts


def generate_resolutions(conflicts: List[Conflict], tracks: List[AirTrack]) -> List[Resolution]:
    """
    Generate resolution maneuvers for detected conflicts.
    Uses simple rules: lower-priority track maneuvers.
    """
    resolutions = []
    
    for conflict in conflicts:
        # Determine which track should maneuver (lower track ID = lower priority for demo)
        primary_id = conflict.track_a
        secondary_id = conflict.track_b
        
        primary = next(t for t in tracks if t.track_id == primary_id)
        secondary = next(t for t in tracks if t.track_id == secondary_id)
        
        # Resolution logic based on conflict type
        if conflict.conflict_type == ConflictType.ALTITUDE:
            # Vertical separation: lower track descends, higher track climbs
            if primary.position[2] <= secondary.position[2]:
                new_alt = max(0, primary.position[2] - 2000)
                resolutions.append(Resolution(
                    conflict=conflict,
                    primary_track=primary_id,
                    resolution_type=ResolutionType.DESCEND,
                    instruction=f"{primary_id}: Descend to {new_alt}ft for vertical separation",
                    new_altitude=int(new_alt)
                ))
            else:
                new_alt = primary.position[2] + 2000
                resolutions.append(Resolution(
                    conflict=conflict,
                    primary_track=primary_id,
                    resolution_type=ResolutionType.CLIMB,
                    instruction=f"{primary_id}: Climb to {new_alt}ft for vertical separation",
                    new_altitude=int(new_alt)
                ))
        
        elif conflict.conflict_type == ConflictType.PROXIMITY:
            # Lateral separation: turn to increase lateral distance
            hdg = primary.velocity[0]
            new_hdg = (hdg + 45) % 360
            resolutions.append(Resolution(
                conflict=conflict,
                primary_track=primary_id,
                resolution_type=ResolutionType.TURN_RIGHT,
                instruction=f"{primary_id}: Turn right to {new_hdg}° for lateral separation",
                new_heading=new_hdg
            ))
        
        elif conflict.conflict_type == ConflictType.CROSSING:
            # Speed adjustment: slow down to let other track pass
            spd = primary.velocity[1]
            new_spd = max(120, spd - 50)
            resolutions.append(Resolution(
                conflict=conflict,
                primary_track=primary_id,
                resolution_type=ResolutionType.SLOW_DOWN,
                instruction=f"{primary_id}: Reduce speed to {new_spd}kts to allow {secondary_id} to pass",
                new_speed=int(new_spd)
            ))
    
    return resolutions


def create_sample_tracks() -> List[AirTrack]:
    """Create sample track data for demonstration."""
    tracks = [
        AirTrack(
            track_id="AC001",
            track_type="AIR",
            position=(0.0, 0.0, 35000),
            velocity=(90, 450),  # East, 450 kts
            callsign="EAGLE 1",
            flight_plan="KLAX → KJFK"
        ),
        AirTrack(
            track_id="AC002",
            track_type="AIR",
            position=(15.0, 5.0, 35000),
            velocity=(270, 420),  # West, 420 kts — head-on with AC001
            callsign="HAWK 2",
            flight_plan="KJFK → KLAX"
        ),
        AirTrack(
            track_id="AC003",
            track_type="AIR",
            position=(30.0, 20.0, 25000),
            velocity=(180, 380),  # South, 380 kts
            callsign="FALCON 3",
            flight_plan="KORD → KATL"
        ),
        AirTrack(
            track_id="UAV01",
            track_type="UAV",
            position=(8.0, 12.0, 15000),
            velocity=(45, 150),  # NE, 150 kts
            callsign="REAPER 1",
            flight_plan="ISR PATROL"
        ),
        AirTrack(
            track_id="CM001",
            track_type="CM",
            position=(50.0, 50.0, 500),
            velocity=(315, 550),  # NW, 550 kts — cruise missile
            callsign="TOMAHWK 1",
            flight_plan="STRIKE MISSION"
        ),
        AirTrack(
            track_id="HELO1",
            track_type="HELO",
            position=(5.0, 3.0, 500),
            velocity=(120, 120),  # SE, 120 kts
            callsign="BLACKHAWK 1",
            flight_plan="TAC SUPPORT"
        ),
    ]
    return tracks


def print_separator(char: str = "=", length: int = 70):
    """Print a visual separator line."""
    print(char * length)


def main():
    """Run the airspace deconfliction demonstration."""
    print_separator()
    print("  Apex_JADC2 — Airspace Deconfliction Demonstration")
    print_separator()
    
    tracks = create_sample_tracks()
    
    # Display all tracks
    print("\n📡 ACTIVE TRACKS IN AIRSPACE:")
    print_separator("-")
    print(f"{'ID':<10} {'Type':<8} {'Position (NM)':<25} {'Alt(ft)':<10} {'Hdg(°)':<8} {'Spd(kts)':<10} {'Callsign':<15}")
    print_separator("-")
    for t in tracks:
        pos_str = f"({t.position[0]:.1f}, {t.position[1]:.1f})"
        print(f"{t.track_id:<10} {t.track_type:<8} {pos_str:<25} {t.position[2]:<10} {t.velocity[0]:<8} {t.velocity[1]:<10} {t.callsign:<15}")
    
    # Detect conflicts
    print("\n🔍 SCANNING FOR CONFLICTS...")
    print_separator("-")
    
    conflicts = detect_conflicts(tracks)
    
    if not conflicts:
        print("\n  ✅ NO CONFLICTS DETECTED — Airspace is deconflicted")
    else:
        print(f"\n  ⚠️  {len(conflicts)} CONFLICT(S) DETECTED:\n")
        
        for i, c in enumerate(conflicts, 1):
            severity_icon = {
                "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"
            }.get(c.severity, "⚪")
            
            print(f"  Conflict #{i}: {severity_icon} [{c.severity}] {c.conflict_type.value}")
            print(f"    Tracks: {c.track_a} ↔ {c.track_b}")
            print(f"    Time to conflict: {c.time_to_conflict_min} min")
            print(f"    Distance at CPA: {c.distance_at_conflict_nm} NM")
            print(f"    Description: {c.description}")
            print()
        
        # Generate resolutions
        print_separator()
        print("  RESOLUTION MANEUVERS")
        print_separator()
        
        resolutions = generate_resolutions(conflicts, tracks)
        
        for i, r in enumerate(resolutions, 1):
            print(f"\n  Resolution #{i} for {r.conflict.track_a} ↔ {r.conflict.track_b}:")
            print(f"    Track: {r.primary_track}")
            print(f"    Action: {r.resolution_type.value}")
            print(f"    Instruction: {r.instruction}")
            if r.new_heading is not None:
                print(f"    New Heading: {r.new_heading}°")
            if r.new_altitude is not None:
                print(f"    New Altitude: {r.new_altitude} ft")
            if r.new_speed is not None:
                print(f"    New Speed: {r.new_speed} kts")
    
    # Summary
    print("\n")
    print_separator()
    print("  DECONFLICTION SUMMARY")
    print_separator()
    
    print(f"\n  Total Tracks Monitored: {len(tracks)}")
    print(f"  Conflicts Detected:     {len(conflicts)}")
    print(f"  Resolutions Generated:  {len(conflicts)}")
    
    if conflicts:
        critical = sum(1 for c in conflicts if c.severity == "CRITICAL")
        high = sum(1 for c in conflicts if c.severity == "HIGH")
        medium = sum(1 for c in conflicts if c.severity == "MEDIUM")
        low = sum(1 for c in conflicts if c.severity == "LOW")
        
        print(f"\n  Severity Breakdown:")
        print(f"    🔴 Critical: {critical}")
        print(f"    🟠 High:     {high}")
        print(f"    🟡 Medium:   {medium}")
        print(f"    🟢 Low:      {low}")
    
    print_separator()
    print("  DECONFLICTION DEMONSTRATION COMPLETE")
    print_separator()


if __name__ == "__main__":
    main()
