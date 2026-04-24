"""Refresh service: coordina adapter, aggiorna cache, gestisce errori parziali."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.datasource.adapters.base import BuildRecord
from backend.datasource.adapters.poe_ladder import PoELadderAdapter
from backend.datasource.adapters.pobbin import PobBinAdapter
from backend.datasource.adapters.maxroll import MaxrollAdapter
from backend.datasource.adapters.mobalytics import MobalyticsAdapter
from backend.services.cache_store import load_cache, save_cache

logger = logging.getLogger(__name__)

ALL_ADAPTERS = [
    PoELadderAdapter(),
    PobBinAdapter(),
    MaxrollAdapter(),
    MobalyticsAdapter(),
]


async def refresh_cache(
    league: str = "Mirage",
    sources: Optional[list[str]] = None,
    limit_per_source: int = 100,
) -> dict:
    """
    Esegue refresh della cache per la league specificata.
    Se `sources` è None, aggiorna tutte le fonti attive.
    Ritorna un report con status per ogni source.
    """
    logger.info("Starting cache refresh for league=%s sources=%s", league, sources or "all")
    cache = load_cache(league)
    existing_ids = {b["id"] for b in cache.get("builds", [])}
    new_builds: list[dict] = []
    report: dict[str, dict] = {}

    for adapter in ALL_ADAPTERS:
        if sources and adapter.source_name not in sources:
            report[adapter.source_name] = {"status": "skipped", "count": 0, "error": None}
            continue

        if adapter.source_name == "mobalytics":
            report["mobalytics"] = {"status": "skipped", "count": 0, "error": None}
            continue

        try:
            records: list[BuildRecord] = await adapter.fetch(league=league, limit=limit_per_source)
            ts = datetime.now(timezone.utc).isoformat()
            count = 0
            for rec in records:
                d = rec.to_dict()
                if d["id"] not in existing_ids:
                    new_builds.append(d)
                    existing_ids.add(d["id"])
                    count += 1
            cache["sources"][adapter.source_name] = {
                "status": "ok",
                "count": count,
                "updated_at": ts,
                "error": None,
            }
            report[adapter.source_name] = {"status": "ok", "count": count, "error": None}
            logger.info("%s: +%d new builds", adapter.source_name, count)
        except Exception as exc:
            logger.error("Adapter %s failed: %s", adapter.source_name, exc)
            ts = datetime.now(timezone.utc).isoformat()
            cache["sources"][adapter.source_name] = {
                "status": "error",
                "count": 0,
                "updated_at": ts,
                "error": str(exc),
            }
            report[adapter.source_name] = {"status": "error", "count": 0, "error": str(exc)}

    # Merge new builds into cache
    cache["builds"] = cache.get("builds", []) + new_builds
    save_cache(league, cache)

    return {
        "league": league,
        "new_builds_added": len(new_builds),
        "total_builds": len(cache["builds"]),
        "sources": report,
    }
