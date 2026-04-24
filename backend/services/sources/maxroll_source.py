"""FOB: load builds from offline Maxroll catalog (JSON)."""

from __future__ import annotations
import json
from pathlib import Path
from backend.services.fob_oracle import Build, BuildQuery
from backend.datasource.adapters.base import BuildRecord


class MaxrollBuildsSource:
    """Load builds from offline Maxroll seed JSON (data/build_seeds/mirage.json)."""

    def __init__(self, catalog_path: str | Path):
        self.catalog_path = Path(catalog_path)
        self._builds: list[BuildRecord] = []

    async def load(self):
        """Load catalog from JSON file."""
        if not self.catalog_path.exists():
            return
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        for item in data:
            # Convert seed JSON to BuildRecord
            rec = BuildRecord(
                id=item["id"],
                league=item.get("league", "Mirage"),
                source=item["source"],
                category=item["category"],
                name=item["name"],
                url=item.get("url"),
                author=item.get("author"),
                ascendancy=item.get("ascendancy"),
                class_name=item.get("class_name"),
                main_skill=item.get("main_skill"),
                tags=item.get("tags", {}),
                guide=item.get("guide", {}),
                raw=item,
                signals=item.get("signals", {})
            )
            self._builds.append(rec)

    async def fetch_builds(self, query: BuildQuery) -> list[Build]:
        """Return all loaded builds."""
        return self._builds
