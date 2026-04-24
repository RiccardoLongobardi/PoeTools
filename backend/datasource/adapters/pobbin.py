"""Adapter: pobb.in — build share site."""
from __future__ import annotations

import hashlib
import logging

import httpx

from backend.datasource.adapters.base import BuildAdapter, BuildRecord

logger = logging.getLogger(__name__)

# pobb.in espone una API non documentata ma usata dal sito
POBBIN_SEARCH_URL = "https://pobb.in/api/search?q=&league={league}&page=1&per_page={limit}"
USER_AGENT = "PoeTools/FOBOracle (contact: github.com/RiccardoLongobardi/PoeTools)"


class PobBinAdapter(BuildAdapter):
    source_name = "pobbin"

    async def fetch(self, league: str, limit: int = 100) -> list[BuildRecord]:
        url = POBBIN_SEARCH_URL.format(league=league, limit=min(limit, 100))
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        records: list[BuildRecord] = []

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("pobb.in fetch failed: %s", exc)
            return []

        items = data if isinstance(data, list) else data.get("data", data.get("builds", []))
        for item in items:
            slug = item.get("id") or item.get("slug", "")
            title = item.get("title") or item.get("name", "Unknown Build")
            main_skill = item.get("mainSkill") or item.get("main_skill", "")
            ascendancy = item.get("ascendancy", "")
            author = item.get("author") or item.get("user", {}).get("name", "unknown")

            build_id = hashlib.md5(f"pobbin:{slug}".encode()).hexdigest()[:12]

            rec = BuildRecord(
                id=build_id,
                league=league,
                source="pobbin",
                category="guide",
                name=title,
                url=f"https://pobb.in/{slug}" if slug else None,
                author=author,
                ascendancy=ascendancy,
                main_skill=main_skill,
                tags={
                    "element": _extract_list(item, "elements", "element"),
                    "damage_type": _extract_list(item, "damageTypes", "damage_types"),
                    "playstyle": _extract_list(item, "playstyle"),
                    "weapon_pref": _extract_list(item, "weaponTypes", "weapon_pref"),
                },
                guide={
                    "summary": item.get("description", ""),
                    "pros": [],
                    "cons": [],
                    "levelling": [],
                    "gear": [],
                    "notes": "",
                },
                raw={"raw_text": item.get("description", ""), "raw_html": ""},
                signals={
                    "is_ladder_build": False,
                    "is_guide_build": True,
                    "confidence": 0.7,
                    "popularity_rank": item.get("views") or item.get("upvotes"),
                },
            )
            records.append(rec)

        logger.info("pobb.in: %d records fetched for %s", len(records), league)
        return records


def _extract_list(item: dict, *keys: str) -> list[str]:
    for k in keys:
        val = item.get(k)
        if isinstance(val, list):
            return [str(v) for v in val]
        if isinstance(val, str) and val:
            return [val]
    return []
