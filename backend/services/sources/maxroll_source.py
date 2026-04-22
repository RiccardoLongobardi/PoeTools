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
