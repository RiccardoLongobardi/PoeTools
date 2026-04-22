"""FOB: build progression planner (1→100)."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from backend.services.fob_oracle import Build, BuildPlan


@dataclass
class LevellingStage:
    level: int
    tree_nodes: list[str] = field(default_factory=list)
    gems: list[str] = field(default_factory=list)


@dataclass
class GearPhase:
    name: str
    items: list[str] = field(default_factory=list)
    cost_div: Optional[float] = None


async def create_build_plan(build: Build) -> BuildPlan:
    """Generate full progression plan for a build."""
    # TODO: implement real levelling stages + gear phases
    return BuildPlan(
        build_id=build.id,
        league=build.league or "Mirage",
        notes="Stub plan - implement tree parsing + gear phases",
    )
