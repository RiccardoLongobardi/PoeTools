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
