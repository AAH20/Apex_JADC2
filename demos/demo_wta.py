#!/usr/bin/env python3
"""
demo_wta.py — Weapon-Target Assignment (WTA) Demonstration
===========================================================

Demonstrates the Weapon-Target Assignment problem for Apex_JADC2.
Given a set of weapon systems and a set of incoming threats, computes
an optimal assignment that maximizes total expected kill probability.

Algorithm: Exhaustive search over all valid assignments (suitable for
small demonstration sizes). For larger problems, the Hungarian algorithm
or auction algorithms would be used.

Usage:
    python3 demo_wta.py
"""

import itertools
import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class Weapon:
    """Represents a weapon system available for assignment."""
    id: str
    name: str
    type: str
    range_km: float
    pk: float  # Base probability of kill against generic target
    quantity: int = 1


@dataclass
class Target:
    """Represents an incoming threat to be engaged."""
    id: str
    name: str
    type: str
    range_km: float
    threat_level: int  # 1-10, higher is more dangerous
    priority: int      # 1-10, higher means engage first


@dataclass
class Assignment:
    """A single weapon-to-target assignment with computed Pk."""
    weapon_id: str
    target_id: str
    pk: float
    range_km: float


@dataclass
class WTAResult:
    """Result of a WTA computation."""
    assignments: List[Assignment] = field(default_factory=list)
    total_pk: float = 0.0
    unassigned_weapons: List[str] = field(default_factory=list)
    unengaged_targets: List[str] = field(default_factory=list)


def compute_engagement_pk(weapon: Weapon, target: Target) -> float:
    """
    Compute probability of kill for a weapon-target pair.
    
    Factors:
    - Base Pk of the weapon
    - Range factor: Pk decreases if target is near weapon's max range
    - Threat level: Higher threat targets are slightly harder to kill
    """
    if target.range_km > weapon.range_km:
        return 0.0  # Target out of range
    
    # Range degradation: linear falloff from 100% at 0 km to 50% at max range
    range_factor = 1.0 - 0.5 * (target.range_km / weapon.range_km)
    
    # Threat difficulty: each threat level above 5 reduces Pk by 3%
    threat_factor = max(0.5, 1.0 - 0.03 * (target.threat_level - 5))
    
    pk = weapon.pk * range_factor * threat_factor
    return round(min(0.99, max(0.01, pk)), 4)


def solve_wta(weapons: List[Weapon], targets: List[Target]) -> WTAResult:
    """
    Solve the Weapon-Target Assignment problem.
    
    Uses exhaustive search over all possible assignments to find the
    assignment that maximizes total expected kill probability.
    
    Each weapon can be assigned to at most one target.
    Each target can be engaged by at most one weapon.
    """
    if not weapons or not targets:
        return WTAResult()
    
    # Build Pk matrix
    pk_matrix: Dict[Tuple[str, str], float] = {}
    for w in weapons:
        for t in targets:
            pk = compute_engagement_pk(w, t)
            if pk > 0:
                pk_matrix[(w.id, t.id)] = pk
    
    # Generate all valid assignments (one weapon per target, one target per weapon)
    best_result = WTAResult()
    n = min(len(weapons), len(targets))
    
    # Try all permutations of weapon-to-target assignments
    weapon_ids = [w.id for w in weapons]
    target_ids = [t.id for t in targets]
    
    for perm in itertools.permutations(target_ids, min(len(weapon_ids), len(target_ids))):
        assignments = []
        total_pk = 0.0
        used_weapons = set()
        used_targets = set()
        
        for i, wid in enumerate(weapon_ids[:len(perm)]):
            tid = perm[i]
            pk = pk_matrix.get((wid, tid), 0.0)
            if pk > 0:
                assignments.append(Assignment(
                    weapon_id=wid,
                    target_id=tid,
                    pk=pk,
                    range_km=next(t.range_km for t in targets if t.id == tid)
                ))
                total_pk += pk
                used_weapons.add(wid)
                used_targets.add(tid)
        
        if total_pk > best_result.total_pk:
            best_result = WTAResult(
                assignments=assignments,
                total_pk=round(total_pk, 4),
                unassigned_weapons=[w for w in weapon_ids if w not in used_weapons],
                unengaged_targets=[t for t in target_ids if t not in used_targets]
            )
    
    return best_result


def create_sample_data() -> Tuple[List[Weapon], List[Target]]:
    """Create sample weapon and target data for demonstration."""
    weapons = [
        Weapon(id="W01", name="Patriot PAC-3", type="SAM", range_km=35.0, pk=0.85, quantity=4),
        Weapon(id="W02", name="THAAD", type="ABM", range_km=200.0, pk=0.90, quantity=2),
        Weapon(id="W03", name="NASAMS", type="SAM", range_km=25.0, pk=0.75, quantity=6),
        Weapon(id="W04", name="Iron Dome", type="C-RAM", range_km=70.0, pk=0.80, quantity=3),
        Weapon(id="W05", name="Aegis SM-6", type="SAM", range_km=240.0, pk=0.88, quantity=4),
    ]
    
    targets = [
        Target(id="T01", name="Cruise Missile Alpha", type="CM", range_km=28.0, threat_level=7, priority=9),
        Target(id="T02", name="Fighter Bomber", type="AIR", range_km=15.0, threat_level=8, priority=10),
        Target(id="T03", name="Ballistic Missile", type="BM", range_km=180.0, threat_level=10, priority=10),
        Target(id="T04", name="UAV Swarm Node", type="UAV", range_km=8.0, threat_level=4, priority=5),
        Target(id="T05", name="Cruise Missile Bravo", type="CM", range_km=32.0, threat_level=7, priority=8),
        Target(id="T06", name="Attack Helicopter", type="HELO", range_km=12.0, threat_level=6, priority=7),
    ]
    
    return weapons, targets


def print_separator(char: str = "=", length: int = 70):
    """Print a visual separator line."""
    print(char * length)


def main():
    """Run the WTA demonstration."""
    print_separator()
    print("  Apex_JADC2 — Weapon-Target Assignment (WTA) Demonstration")
    print_separator()
    
    # Load sample data
    weapons, targets = create_sample_data()
    
    # Display available weapons
    print("\n📡 AVAILABLE WEAPON SYSTEMS:")
    print_separator("-")
    print(f"{'ID':<6} {'Name':<20} {'Type':<8} {'Range(km)':<12} {'Base Pk':<10} {'Qty':<5}")
    print_separator("-")
    for w in weapons:
        print(f"{w.id:<6} {w.name:<20} {w.type:<8} {w.range_km:<12.1f} {w.pk:<10.2f} {w.quantity:<5}")
    
    # Display incoming threats
    print("\n🎯 INCOMING THREATS:")
    print_separator("-")
    print(f"{'ID':<6} {'Name':<25} {'Type':<8} {'Range(km)':<12} {'Threat':<8} {'Priority':<8}")
    print_separator("-")
    for t in targets:
        print(f"{t.id:<6} {t.name:<25} {t.type:<8} {t.range_km:<12.1f} {t.threat_level:<8} {t.priority:<8}")
    
    # Compute Pk matrix
    print("\n📊 ENGAGEMENT PROBABILITY MATRIX (Pk):")
    print_separator("-")
    header = f"{'Weapon':<12}" + "".join(f"{t.id:<8}" for t in targets)
    print(header)
    print_separator("-")
    for w in weapons:
        row = f"{w.id:<12}"
        for t in targets:
            pk = compute_engagement_pk(w, t)
            row += f"{pk:<8.3f}" if pk > 0 else f"{'---':<8}"
        print(row)
    
    # Solve WTA
    print("\n⚙️  SOLVING WEAPON-TARGET ASSIGNMENT...")
    print_separator("-")
    result = solve_wta(weapons, targets)
    
    # Display results
    print("\n✅ OPTIMAL ASSIGNMENT:")
    print_separator("-")
    print(f"{'Weapon':<12} {'→ Target':<12} {'Pk':<10} {'Range(km)':<12}")
    print_separator("-")
    for a in result.assignments:
        w_name = next(w.name for w in weapons if w.id == a.weapon_id)
        t_name = next(t.name for t in targets if t.id == a.target_id)
        print(f"{a.weapon_id} ({w_name[:8]:<8}) → {a.target_id} ({t_name[:10]:<10}) {a.pk:<10.3f} {a.range_km:<12.1f}")
    
    print_separator("-")
    print(f"\n📈 TOTAL EXPECTED KILL PROBABILITY: {result.total_pk:.4f}")
    print(f"   (Expected number of kills: {result.total_pk:.2f} out of {len(targets)} threats)")
    
    if result.unassigned_weapons:
        print(f"\n🔸 UNASSIGNED WEAPONS: {', '.join(result.unassigned_weapons)}")
    if result.unengaged_targets:
        print(f"🔸 UNENGAGED TARGETS:  {', '.join(result.unengaged_targets)}")
    
    # Summary
    print_separator()
    print("  WTA DEMONSTRATION COMPLETE")
    print_separator()


if __name__ == "__main__":
    main()
