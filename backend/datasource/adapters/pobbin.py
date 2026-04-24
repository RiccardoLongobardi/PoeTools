"""Adapter: poe.ninja builds — sostituisce pobb.in (nessuna API pubblica stabile).

poe.ninja espone dati aggregati di build per ascendancy + main skill su:
  GET https://poe.ninja/api/data/builds?league={league}&type=exp&limit={limit}

Restituisce array di entry con ascendancy, mainSkill, pobUrl (quando presente),
usage count e rank. È l'unica fonte pubblica con PoB URL reali non privati.
"""
from __future__ import annotations

import hashlib
import logging

import httpx

from backend.datasource.adapters.base import BuildAdapter, BuildRecord

logger = logging.getLogger(__name__)

NINJA_BUILDS_URL = (
    "https://poe.ninja/api/data/builds"
    "?league={league}&type=exp&limit={limit}"
)
USER_AGENT = "PoeTools/FOBOracle (contact: github.com/RiccardoLongobardi/PoeTools)"


class PobBinAdapter(BuildAdapter):
    """Nome mantenuto per compatibilità con refresh_service, ora punta a poe.ninja builds."""

    source_name = "pobbin"

    async def fetch(self, league: str, limit: int = 100) -> list[BuildRecord]:
        url = NINJA_BUILDS_URL.format(league=league, limit=min(limit, 500))
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        records: list[BuildRecord] = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("poe.ninja builds fetch failed: %s", exc)
            return []

        # poe.ninja risponde con {"lines": [...], "language": {...}}
        lines = data.get("lines", [])
        if not lines:
            # Fallback: a volte la risposta è una lista diretta
            lines = data if isinstance(data, list) else []

        for item in lines:
            ascendancy = item.get("ascendancyOrClass", "") or item.get("ascendancy", "")
            main_skill = item.get("mainSkill", "") or item.get("skill", "")
            pob_url = item.get("pobUrl") or item.get("pob_url") or None
            rank = item.get("rank") or item.get("count") or None
            name_parts = [p for p in [ascendancy, main_skill] if p]
            name = " – ".join(name_parts) if name_parts else "Unknown Build"

            slug = f"ninja:{league}:{ascendancy}:{main_skill}"
            build_id = hashlib.md5(slug.encode()).hexdigest()[:12]

            # Estrai elementi/damage type dai tag poe.ninja se presenti
            skills_used = item.get("skillsUsed") or []
            elements = [
                s for s in skills_used
                if any(e in s.lower() for e in ("fire", "cold", "lightning", "chaos", "physical"))
            ]

            rec = BuildRecord(
                id=build_id,
                league=league,
                source="pobbin",
                category="meta",
                name=name,
                url=pob_url,
                author="poe.ninja",
                ascendancy=ascendancy,
                main_skill=main_skill,
                tags={
                    "element": elements,
                    "damage_type": [],
                    "playstyle": [],
                    "weapon_pref": [],
                },
                guide={
                    "summary": f"Build aggregata da poe.ninja per {ascendancy} – {main_skill}.",
                    "pros": [],
                    "cons": [],
                    "levelling": [],
                    "gear": [],
                    "notes": "",
                },
                raw={"raw_text": "", "raw_html": ""},
                signals={
                    "is_ladder_build": False,
                    "is_guide_build": False,
                    "is_ninja_build": True,
                    "confidence": 0.85,
                    "popularity_rank": rank,
                    "usage_count": item.get("count"),
                },
            )
            records.append(rec)

        logger.info("poe.ninja builds: %d records fetched for %s", len(records), league)
        return records
