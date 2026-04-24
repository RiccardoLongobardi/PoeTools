"""Adapter: Maxroll.gg build guides (offline seed JSON)."""
from __future__ import annotations
from pathlib import Path

from backend.datasource.adapters.base import BuildAdapter, BuildRecord
from backend.services.sources.maxroll_source import MaxrollBuildsSource


class MaxrollAdapter(BuildAdapter):
    source_name = "maxroll"

    def __init__(self, seed_path: str | Path = "data/build_seeds/mirage.json"):
        self.seed_path = Path(seed_path)
        self.source = MaxrollBuildsSource(catalog_path=self.seed_path)

    async def fetch(self, league: str, limit: int = 100) -> list[BuildRecord]:
        """Load builds from offline seed JSON."""
        await self.source.load()
        # Filter by league if needed, return up to limit
        builds = self.source._builds
        # For Mirage league, all seeds match; for other leagues filter
        if league.lower() != "mirage":
            builds = [b for b in builds if b.league and b.league.lower() == league.lower()]
        return builds[:limit]
