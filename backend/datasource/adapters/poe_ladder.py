"""Adapter: PoE Official Ladder API."""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

from backend.datasource.adapters.base import BuildAdapter, BuildRecord

logger = logging.getLogger(__name__)

LADDER_URL = "https://api.pathofexile.com/ladders/{league}?limit={limit}&offset=0"
USER_AGENT = "PoeTools/FOBOracle (contact: github.com/RiccardoLongobardi/PoeTools)"

# Mapping class → ascendancy lookup semplice (espandibile)
CLASS_ASCENDANCIES: dict[str, list[str]] = {
    "Witch": ["Necromancer", "Occultist", "Elementalist"],
    "Shadow": ["Assassin", "Saboteur", "Trickster"],
    "Ranger": ["Pathfinder", "Raider", "Deadeye"],
    "Duelist": ["Slayer", "Gladiator", "Champion"],
    "Marauder": ["Juggernaut", "Berserker", "Chieftain"],
    "Templar": ["Inquisitor", "Hierophant", "Guardian"],
    "Scion": ["Ascendant"],
}


class PoELadderAdapter(BuildAdapter):
    source_name = "ladder"

    async def fetch(self, league: str, limit: int = 200) -> list[BuildRecord]:
        url = LADDER_URL.format(league=league, limit=min(limit, 200))
        headers = {"User-Agent": USER_AGENT}
        records: list[BuildRecord] = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("PoE ladder fetch failed: %s", exc)
            return []

        entries = data.get("entries", [])
        for rank, entry in enumerate(entries, start=1):
            char = entry.get("character", {})
            account = entry.get("account", {})
            char_name = char.get("name", "")
            class_name = char.get("class", "")
            level = char.get("level", 0)
            depth = char.get("depth", {}).get("solo", 0)

            build_id = hashlib.md5(f"ladder:{league}:{char_name}".encode()).hexdigest()[:12]

            rec = BuildRecord(
                id=build_id,
                league=league,
                source="ladder",
                category="meta",
                name=f"{class_name} (Rank {rank})",
                url=f"https://www.pathofexile.com/account/view-profile/{account.get('name', '')}/characters",
                author=account.get("name", "unknown"),
                class_name=class_name,
                tags={
                    "element": [],
                    "damage_type": [],
                    "playstyle": [],
                    "weapon_pref": [],
                },
                signals={
                    "is_ladder_build": True,
                    "is_guide_build": False,
                    "confidence": 1.0,
                    "popularity_rank": rank,
                    "level": level,
                    "depth": depth,
                },
            )
            records.append(rec)

        logger.info("PoE ladder: %d records fetched for %s", len(records), league)
        return records
