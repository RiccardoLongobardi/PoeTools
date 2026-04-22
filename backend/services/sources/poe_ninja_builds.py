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
