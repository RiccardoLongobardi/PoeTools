# FOB Complete Setup Script per Windows
Write-Host "Creating FOB files..." -ForegroundColor Green

# Create directories
New-Item -ItemType Directory -Force -Path "backend\services\sources" | Out-Null
New-Item -ItemType Directory -Force -Path "backend\services\pricing" | Out-Null

# sources/__init__.py
@"
"""FOB build sources package."""

from .poe_ninja_builds import PoeNinjaBuildsSource
from .maxroll_source import MaxrollBuildsSource
from .forum_source import ForumBuildsSource

__all__ = [
    "PoeNinjaBuildsSource",
    "MaxrollBuildsSource",
    "ForumBuildsSource",
]
"@ | Out-File -FilePath "backend\services\sources\__init__.py" -Encoding UTF8

Write-Host "Created sources/__init__.py" -ForegroundColor Cyan

# sources/poe_ninja_builds.py
@"
"""FOB: fetch builds from poe.ninja via GGG ladder + character API."""

from __future__ import annotations
from typing import Optional
import httpx
from backend.services.fob_oracle import Build, BuildQuery


class PoeNinjaBuildsSource:
    """Fetch builds from PoE ladder + poe.ninja economy data."""

    def __init__(self, league: str = "Mirage", top_n: int = 100):
        self.league = league
        self.top_n = top_n

    async def fetch_builds(self, query: BuildQuery) -> list[Build]:
        """TODO: implement ladder fetch + character API parsing."""
        return []
"@ | Out-File -FilePath "backend\services\sources\poe_ninja_builds.py" -Encoding UTF8

Write-Host "Created poe_ninja_builds.py" -ForegroundColor Cyan

# sources/maxroll_source.py
@"
"""FOB: load builds from offline Maxroll catalog (JSON)."""

from __future__ import annotations
import json
from pathlib import Path
from backend.services.fob_oracle import Build, BuildQuery
from backend.services.pob_parser import parse_pob


class MaxrollBuildsSource:
    """Load builds from offline Maxroll catalog JSON."""

    def __init__(self, catalog_path: str | Path):
        self.catalog_path = Path(catalog_path)
        self._builds: list[Build] = []

    async def load(self):
        """Load catalog from JSON file."""
        if not self.catalog_path.exists():
            return
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # TODO: parse catalog and populate self._builds

    async def fetch_builds(self, query: BuildQuery) -> list[Build]:
        """Return all loaded builds."""
        return self._builds
"@ | Out-File -FilePath "backend\services\sources\maxroll_source.py" -Encoding UTF8

Write-Host "Created maxroll_source.py" -ForegroundColor Cyan

# sources/forum_source.py
@"
"""FOB: load builds from offline PoE forum catalog (JSON)."""

from __future__ import annotations
from .maxroll_source import MaxrollBuildsSource


class ForumBuildsSource(MaxrollBuildsSource):
    """Load builds from offline forum catalog JSON."""

    async def fetch_builds(self, query):
        builds = await super().fetch_builds(query)
        for b in builds:
            b.source = "forum"
        return builds
"@ | Out-File -FilePath "backend\services\sources\forum_source.py" -Encoding UTF8

Write-Host "Created forum_source.py" -ForegroundColor Cyan

# pricing/__init__.py
@"
"""FOB pricing modules."""

from .poe_ninja_pricing import estimate_item_cost_poe_ninja
from .trade_pricing import estimate_item_cost_trade

__all__ = [
    "estimate_item_cost_poe_ninja",
    "estimate_item_cost_trade",
]
"@ | Out-File -FilePath "backend\services\pricing\__init__.py" -Encoding UTF8

Write-Host "Created pricing/__init__.py" -ForegroundColor Cyan

# pricing/poe_ninja_pricing.py
@"
"""FOB: item pricing via poe.ninja itemoverview API."""

from __future__ import annotations
import httpx
from typing import Optional


async def estimate_item_cost_poe_ninja(
    item_name: str, item_type: str, league: str = "Mirage"
) -> Optional[float]:
    """Estimate item cost in divines using poe.ninja itemoverview."""
    url = f"https://poe.ninja/api/data/itemoverview?league={league}&type={item_type}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            for line in data.get("lines", []):
                if line.get("name") == item_name:
                    return line.get("divineValue") or line.get("chaosValue", 0) / 200.0
        except Exception:
            pass
    
    return None
"@ | Out-File -FilePath "backend\services\pricing\poe_ninja_pricing.py" -Encoding UTF8

Write-Host "Created poe_ninja_pricing.py" -ForegroundColor Cyan

# pricing/trade_pricing.py
@"
"""FOB: item pricing via official trade API."""

from __future__ import annotations
import httpx
from typing import Optional


async def estimate_item_cost_trade(
    item_query: dict, league: str = "Mirage"
) -> Optional[float]:
    """Estimate item cost using official trade API."""
    # TODO: implement POST /api/trade/search + GET /api/trade/fetch
    return None
"@ | Out-File -FilePath "backend\services\pricing\trade_pricing.py" -Encoding UTF8

Write-Host "Created trade_pricing.py" -ForegroundColor Cyan

# planner.py
@"
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
"@ | Out-File -FilePath "backend\services\planner.py" -Encoding UTF8

Write-Host "Created planner.py" -ForegroundColor Cyan

Write-Host "`nAll FOB files created successfully!" -ForegroundColor Green
Write-Host "Next: commit and push to GitHub" -ForegroundColor Yellow