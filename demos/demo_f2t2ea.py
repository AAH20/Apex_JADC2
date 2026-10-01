#!/usr/bin/env python3
"""
demo_f2t2ea.py — F2T2EA Kill Chain Demonstration
================================================

Demonstrates the F2T2EA (Find, Fix, Track, Target, Engage, Assess)
kill chain process for Apex_JADC2 using sample track data.

The kill chain phases:
  1. FIND      — Detect and identify potential threats
  2. FIX       — Determine precise location and classification
  3. TRACK     — Maintain continuous track on the target
  4. TARGET    — Select weapon and compute firing solution
  5. ENGAGE    — Execute the engagement
  6. ASSESS    — Battle damage assessment and re-attack decision

Usage:
    python3 demo_f2t2ea.py
"""

import time
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class KillChainPhase(Enum):
    """F2T2EA kill chain phases."""
    FIND = "Find"
    FIX = "Fix"
    TRACK = "Track"
    TARGET = "Target"
    ENGAGE = "Engage"
    ASSESS = "Assess"


class TrackStatus(Enum):
    """Status of a track through the kill chain."""
    DETECTED = "Detected"
    CLASSIFIED = "Classified"
    TRACKED = "Tracked"
    TARGETED = "Targeted"
    ENGAGED = "Engaged"
    DESTROYED = "Destroyed"
    MISSED = "Missed"


@dataclass
class Track:
    """Represents an air/surface track in the battlespace."""
    track_id: str
    track_type: str  # AIR, CM, BM, UAV, HELO, SURFACE
    position: tuple  # (lat, lon, alt_m)
    velocity: tuple  # (heading_deg, speed_mps)
    classification: str = "UNKNOWN"
    threat_level: int = 0
    status: TrackStatus = TrackStatus.DETECTED
    current_phase: KillChainPhase = KillChainPhase.FIND
    history: List[Dict] = field(default_factory=list)
    engaged_by: Optional[str] = None
    assessment: Optional[str] = None


@dataclass
class EngagementResult:
    """Result of an engagement."""
    track_id: str
    weapon: str
    pk: float
    outcome: str  # "DESTROYED" or "MISSED"
    timestamp: float


def phase_find(track: Track) -> bool:
    """
    FIND phase: Detect and identify potential threats.
    Simulates sensor detection with probability based on track type.
    """
    detection_prob = {
        "AIR": 0.95, "CM": 0.85, "BM": 0.90,
        "UAV": 0.70, "HELO": 0.80, "SURFACE": 0.95
    }
    prob = detection_prob.get(track.track_type, 0.75)
    detected = random.random() < prob
    
    track.history.append({
        "phase": "FIND",
        "result": "DETECTED" if detected else "NOT_DETECTED",
        "confidence": round(prob, 2)
    })
    
    if detected:
        track.status = TrackStatus.DETECTED
    return detected


def phase_fix(track: Track) -> bool:
    """
    FIX phase: Determine precise location and classification.
    Simulates classification with sensor fusion confidence.
    """
    classification_map = {
        "AIR": ["Fighter", "Bomber", "Transport", "Unknown"],
        "CM": ["Cruise Missile", "Anti-Ship Missile", "Unknown"],
        "BM": ["SRBM", "MRBM", "IRBM", "Unknown"],
        "UAV": ["Recon UAV", "Attack UAV", "Decoy", "Unknown"],
        "HELO": ["Attack Helo", "Transport Helo", "Unknown"],
        "SURFACE": ["Combatant", "Auxiliary", "Unknown"]
    }
    
    options = classification_map.get(track.track_type, ["Unknown"])
    weights = [0.5, 0.3, 0.15, 0.05]
    track.classification = random.choices(options, weights=weights[:len(options)])[0]
    
    # Threat level based on classification
    threat_map = {
        "Fighter": 8, "Bomber": 7, "Transport": 3,
        "Cruise Missile": 7, "Anti-Ship Missile": 8,
        "SRBM": 10, "MRBM": 9, "IRBM": 8,
        "Recon UAV": 4, "Attack UAV": 6, "Decoy": 1,
        "Attack Helo": 6, "Transport Helo": 2,
        "Combatant": 7, "Auxiliary": 3, "Unknown": 5
    }
    track.threat_level = threat_map.get(track.classification, 5)
    track.status = TrackStatus.CLASSIFIED
    
    track.history.append({
        "phase": "FIX",
        "classification": track.classification,
        "threat_level": track.threat_level
    })
    return True


def phase_track(track: Track) -> bool:
    """
    TRACK phase: Maintain continuous track on the target.
    Simulates track maintenance over multiple sensor updates.
    """
    updates = random.randint(3, 8)
    track_quality = random.uniform(0.7, 0.99)
    
    # Simulate track updates
    for i in range(updates):
        # Slight position drift to simulate tracking
        lat, lon, alt = track.position
        hdg, spd = track.velocity
        lat += math.cos(math.radians(hdg)) * spd * 0.00001
        lon += math.sin(math.radians(hdg)) * spd * 0.00001
        track.position = (round(lat, 6), round(lon, 6), alt)
    
    track.status = TrackStatus.TRACKED
    track.history.append({
        "phase": "TRACK",
        "updates": updates,
        "track_quality": round(track_quality, 3)
    })
    return track_quality > 0.6


def phase_target(track: Track) -> Optional[str]:
    """
    TARGET phase: Select weapon and compute firing solution.
    Returns the selected weapon system.
    """
    # Weapon selection based on track type and threat
    weapon_selection = {
        "Fighter": "Patriot PAC-3",
        "Bomber": "THAAD",
        "Cruise Missile": "NASAMS",
        "Anti-Ship Missile": "Aegis SM-6",
        "SRBM": "THAAD",
        "MRBM": "THAAD",
        "IRBM": "Aegis SM-6",
        "Recon UAV": "Iron Dome",
        "Attack UAV": "Iron Dome",
        "Decoy": "Iron Dome",
        "Attack Helo": "NASAMS",
        "Transport Helo": "NASAMS",
        "Combatant": "Aegis SM-6",
        "Auxiliary": "NASAMS",
        "Unknown": "NASAMS"
    }
    
    weapon = weapon_selection.get(track.classification, "NASAMS")
    track.engaged_by = weapon
    track.status = TrackStatus.TARGETED
    
    # Compute firing solution quality
    solution_quality = random.uniform(0.75, 0.98)
    
    track.history.append({
        "phase": "TARGET",
        "weapon": weapon,
        "solution_quality": round(solution_quality, 3)
    })
    return weapon


def phase_engage(track: Track, weapon: str) -> EngagementResult:
    """
    ENGAGE phase: Execute the engagement.
    Simulates weapon launch and intercept.
    """
    # Pk based on weapon and track type
    base_pk = {
        "Patriot PAC-3": 0.85, "THAAD": 0.90, "NASAMS": 0.75,
        "Iron Dome": 0.80, "Aegis SM-6": 0.88
    }
    
    pk = base_pk.get(weapon, 0.70)
    # Adjust for track quality
    pk *= random.uniform(0.85, 1.0)
    pk = min(0.99, pk)
    
    # Determine outcome
    roll = random.random()
    outcome = "DESTROYED" if roll < pk else "MISSED"
    
    track.status = TrackStatus.DESTROYED if outcome == "DESTROYED" else TrackStatus.MISSED
    
    result = EngagementResult(
        track_id=track.track_id,
        weapon=weapon,
        pk=round(pk, 3),
        outcome=outcome,
        timestamp=time.time()
    )
    
    track.history.append({
        "phase": "ENGAGE",
        "weapon": weapon,
        "pk": round(pk, 3),
        "outcome": outcome
    })
    
    return result


def phase_assess(track: Track, engagement: EngagementResult) -> str:
    """
    ASSESS phase: Battle damage assessment and re-attack decision.
    """
    if engagement.outcome == "DESTROYED":
        track.assessment = "TARGET DESTROYED — No re-attack required"
        track.history.append({
            "phase": "ASSESS",
            "result": "DESTROYED",
            "re_attack": False
        })
    else:
        # Missed — decide on re-attack
        re_attack = random.random() < 0.7
        if re_attack:
            track.assessment = "TARGET MISSED — Re-attack recommended"
            track.status = TrackStatus.TRACKED  # Back to track phase
        else:
            track.assessment = "TARGET MISSED — Re-attack not feasible"
        track.history.append({
            "phase": "ASSESS",
            "result": "MISSED",
            "re_attack": re_attack
        })
    
    return track.assessment


def run_kill_chain(track: Track) -> List[EngagementResult]:
    """
    Run the full F2T2EA kill chain for a single track.
    Returns list of engagement results.
    """
    results = []
    
    # Phase 1: FIND
    if not phase_find(track):
        return results  # Not detected, kill chain ends
    
    # Phase 2: FIX
    phase_fix(track)
    
    # Phase 3: TRACK
    if not phase_track(track):
        return results  # Lost track
    
    # Phase 4: TARGET
    weapon = phase_target(track)
    if not weapon:
        return results
    
    # Phase 5: ENGAGE
    engagement = phase_engage(track, weapon)
    results.append(engagement)
    
    # Phase 6: ASSESS
    phase_assess(track, engagement)
    
    # Re-attack if missed and feasible
    if track.status == TrackStatus.TRACKED and track.assessment and "Re-attack recommended" in track.assessment:
        weapon = phase_target(track)
        if weapon is not None:
            engagement = phase_engage(track, weapon)
            results.append(engagement)
            phase_assess(track, engagement)
    
    return results


def create_sample_tracks() -> List[Track]:
    """Create sample track data for demonstration."""
    random.seed(42)  # Reproducible results
    
    tracks = [
        Track(
            track_id="TRK001",
            track_type="CM",
            position=(34.0522, -118.2437, 500),
            velocity=(270, 250)
        ),
        Track(
            track_id="TRK002",
            track_type="AIR",
            position=(34.1000, -118.3000, 8000),
            velocity=(180, 450)
        ),
        Track(
            track_id="TRK003",
            track_type="BM",
            position=(34.2000, -118.1000, 120000),
            velocity=(45, 3000)
        ),
        Track(
            track_id="TRK004",
            track_type="UAV",
            position=(34.0800, -118.2800, 3000),
            velocity=(90, 120)
        ),
        Track(
            track_id="TRK005",
            track_type="HELO",
            position=(34.1200, -118.2200, 500),
            velocity=(120, 80)
        ),
    ]
    return tracks


def print_separator(char: str = "=", length: int = 70):
    """Print a visual separator line."""
    print(char * length)


def main():
    """Run the F2T2EA kill chain demonstration."""
    print_separator()
    print("  Apex_JADC2 — F2T2EA Kill Chain Demonstration")
    print_separator()
    print("  Find → Fix → Track → Target → Engage → Assess")
    print_separator()
    
    tracks = create_sample_tracks()
    
    print(f"\n📡 PROCESSING {len(tracks)} TRACKS THROUGH KILL CHAIN:\n")
    
    all_results = []
    
    for track in tracks:
        print_separator("-")
        print(f"  TRACK: {track.track_id} | Type: {track.track_type}")
        print_separator("-")
        
        results = run_kill_chain(track)
        all_results.extend(results)
        
        # Display kill chain progression
        print(f"\n  Kill Chain Progression:")
        for entry in track.history:
            phase = entry["phase"]
            if phase == "FIND":
                print(f"    🔍 FIND:     {entry['result']} (confidence: {entry['confidence']})")
            elif phase == "FIX":
                print(f"    🎯 FIX:      Classified as {entry['classification']} (threat: {entry['threat_level']})")
            elif phase == "TRACK":
                print(f"    📡 TRACK:    {entry['updates']} updates, quality: {entry['track_quality']}")
            elif phase == "TARGET":
                print(f"    ⚔️  TARGET:   Weapon: {entry['weapon']}, solution: {entry['solution_quality']}")
            elif phase == "ENGAGE":
                outcome_icon = "💥" if entry['outcome'] == "DESTROYED" else "❌"
                print(f"    {outcome_icon} ENGAGE:   {entry['weapon']} → {entry['outcome']} (Pk: {entry['pk']})")
            elif phase == "ASSESS":
                re_attack = "YES" if entry.get('re_attack') else "NO"
                print(f"    📋 ASSESS:   {entry['result']} | Re-attack: {re_attack}")
        
        if track.assessment:
            print(f"\n  Final Assessment: {track.assessment}")
        print()
    
    # Summary
    print_separator()
    print("  KILL CHAIN SUMMARY")
    print_separator()
    
    total_engagements = len(all_results)
    destroyed = sum(1 for r in all_results if r.outcome == "DESTROYED")
    missed = total_engagements - destroyed
    
    print(f"\n  Total Tracks Processed: {len(tracks)}")
    print(f"  Total Engagements:      {total_engagements}")
    print(f"  Targets Destroyed:      {destroyed}")
    print(f"  Targets Missed:         {missed}")
    print(f"  Success Rate:           {destroyed/total_engagements*100:.1f}%" if total_engagements > 0 else "  N/A")
    
    print("\n  Engagement Details:")
    print_separator("-")
    print(f"  {'Track':<10} {'Weapon':<18} {'Pk':<8} {'Outcome':<12}")
    print_separator("-")
    for r in all_results:
        outcome_icon = "💥" if r.outcome == "DESTROYED" else "❌"
        print(f"  {r.track_id:<10} {r.weapon:<18} {r.pk:<8.3f} {outcome_icon} {r.outcome:<10}")
    
    print_separator()
    print("  F2T2EA DEMONSTRATION COMPLETE")
    print_separator()


if __name__ == "__main__":
    main()
