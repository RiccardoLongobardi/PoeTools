"""FOB: build progression planner (leveling + gear phases)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from backend.services.fob_oracle import Build, BuildPlan
from backend.services.pricing.trade_pricing import TradePricer, COMMON_UNIQUES


@dataclass
class LevellingStage:
    level: int
    tree_nodes: list[str] = field(default_factory=list)
    gems: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class GearPhase:
    name: str
    items: list[str] = field(default_factory=list)
    cost_div: Optional[float] = None


async def create_build_plan(build: Build) -> BuildPlan:
    """Generate full progression plan for a build."""
    
    # Levelling stages (generic progression 1-70)
    stages = [
        LevellingStage(
            level=12,
            gems=["Main skill gem", "Support gems (2-3)"],
            notes="Act 1-2: Focus on life nodes and damage"
        ),
        LevellingStage(
            level=40,
            gems=["4-link main skill", "CWDT setup"],
            notes="Act 4-5: Complete lab 1, get ascendancy"
        ),
        LevellingStage(
            level=68,
            gems=["5-link or tabula", "Auras setup"],
            notes="Act 10: Finish campaign, start mapping"
        ),
    ]
    
    # Gear phases with pricing
    archetype = _detect_archetype(build)
    required_uniques = COMMON_UNIQUES.get(archetype, [])
    
    pricer = TradePricer(league=build.league or "Settlers")
    
    # Budget phase
    budget_cost = await pricer.estimate_build_cost(required_uniques[:2] if required_uniques else [])
    
    # Endgame phase  
    endgame_cost = await pricer.estimate_build_cost(required_uniques if required_uniques else [])
    
    phases = [
        GearPhase(
            name="Budget (maps T1-10)",
            items=["Life + res rares", "Tabula Rasa"] + required_uniques[:2],
            cost_div=budget_cost.get("total_divine", 5.0)
        ),
        GearPhase(
            name="Mid-tier (T11-16)",
            items=["Proper 6-link", "Build-enabling uniques"] + required_uniques[:3],
            cost_div=endgame_cost.get("total_divine", 20.0) * 0.6
        ),
        GearPhase(
            name="Endgame (T17, bosses)",
            items=["Min-maxed rares", "All uniques"] + required_uniques,
            cost_div=endgame_cost.get("total_divine", 50.0)
        ),
    ]
    
    total = sum(p.cost_div for p in phases if p.cost_div)
    
    return BuildPlan(
        build_id=build.id,
        league=build.league or "Settlers",
        levelling_stages=stages,
        gear_phases=phases,
        total_cost_div=total,
        notes=f"Estimated total cost: {total:.1f} divine orbs. Archetype: {archetype}"
    )


def _detect_archetype(build: Build) -> str:
    """Detect build archetype from tags."""
    if "cold" in build.element:
        return "cold_spell" if "spell" in build.damage_type else "cold_attack"
    if "fire" in build.element:
        return "fire_dot" if "dot" in build.damage_type else "fire_spell"
    if "lightning" in build.element:
        return "lightning_attack" if "attack" in build.damage_type else "lightning_spell"
    if "chaos" in build.element:
        return "chaos_dot"
    if "physical" in build.element:
        return "physical_melee"
    return "generic"
