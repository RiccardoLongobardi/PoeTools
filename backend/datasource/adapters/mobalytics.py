"""Adapter: Mobalytics PoE builds — placeholder, non attivo in V1."""
from __future__ import annotations

import logging

from backend.datasource.adapters.base import BuildAdapter, BuildRecord

logger = logging.getLogger(__name__)


class MobalyticsAdapter(BuildAdapter):
    source_name = "mobalytics"

    async def fetch(self, league: str, limit: int = 50) -> list[BuildRecord]:
        logger.info("Mobalytics adapter: skipped in V1")
        return []
