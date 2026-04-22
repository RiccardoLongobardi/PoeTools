"""PoE Ladder builds fetcher — scraping lightweight di poe.ninja/builds.

Alternativa pragmatica a chiamare GGG ladder API 200+ volte.
poe.ninja aggrega già i dati, facciamo scraping della pagina HTML.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.services.fob_oracle import Build, BuildQuery

logger = logging.getLogger(__name__)


class PoELadderSource:
    """Fetch build da poe.ninja/builds tramite scraping HTML."""

    def __init__(
        self,
        league: str = "Mirage",
        base_url: str = "https://poe.ninja/poe1",
        timeout_s: float = 10.0,
    ):
        self.league = league
        self.base_url = base_url
        self.timeout_s = timeout_s

    async def fetch_builds(self, query: BuildQuery, limit: int = 50) -> list[Build]:
        """Fetch top builds dalla ladder poe.ninja.

        Args:
            query: BuildQuery con filtri (non ancora usati nel fetch)
            limit: numero massimo di build da restituire

        Returns:
            Lista di Build oggetti con dati reali dalla ladder
        """
        url = f"{self.base_url}/builds"
        logger.info("Fetching builds from %s (league=%s)", url, self.league)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(url, params={"league": self.league})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("poe.ninja builds fetch failed: %s", exc)
            return []

        # Parse HTML per estrarre build
        soup = BeautifulSoup(resp.text, "lxml")
        builds = []

        # poe.ninja usa una table con righe per ogni build
        # Struttura: <tr> con <td> per rank, name, level, class, main skill, etc
        table = soup.find("table", class_="build-table")  # ipotesi class name
        if not table:
            # Fallback: cerca qualsiasi table
            table = soup.find("table")

        if not table:
            logger.warning("No table found in poe.ninja/builds HTML")
            return []

        rows = table.find_all("tr")[1:]  # skip header
        for i, row in enumerate(rows[:limit]):
            try:
                build = self._parse_build_row(row, i)
                if build:
                    builds.append(build)
            except Exception as exc:
                logger.warning("Failed to parse build row %d: %s", i, exc)
                continue

        logger.info("Parsed %d builds from poe.ninja", len(builds))
        return builds

    def _parse_build_row(self, row, index: int) -> Optional[Build]:
        """Estrae Build da una riga HTML della tabella poe.ninja."""
        cols = row.find_all("td")
        if len(cols) < 5:
            return None

        # Estrai dati (adatta in base alla struttura reale)
        # Ipotesi: cols = [rank, name, level, class, main_skill, ...]
        try:
            name_col = cols[1].get_text(strip=True)
            class_col = cols[3].get_text(strip=True)
            skill_col = cols[4].get_text(strip=True) if len(cols) > 4 else "Unknown"

            # Estrai ascendancy da class (es. "Occultist" da "Witch (Occultist)")
            ascendancy_match = re.search(r"\(([^)]+)\)", class_col)
            ascendancy = ascendancy_match.group(1) if ascendancy_match else class_col

            # Inferisci element/damage_type da skill name
            element = self._infer_element(skill_col)
            damage_type = self._infer_damage_type(skill_col)

            return Build(
                id=f"poeninja_{self.league}_{index}",
                name=f"{name_col} - {skill_col}",
                source="poe.ninja",
                url=f"{self.base_url}/challenge/builds",
                ascendancy=ascendancy,
                main_skill=skill_col,
                element=element,
                damage_type=damage_type,
                league=self.league,
            )
        except Exception as exc:
            logger.debug("Parse error in row: %s", exc)
            return None

    def _infer_element(self, skill: str) -> list[str]:
        """Inferisce element da skill name."""
        skill_lower = skill.lower()
        elem = []
        if any(k in skill_lower for k in ["ice", "cold", "frost", "glacial"]):
            elem.append("cold")
        if any(k in skill_lower for k in ["fire", "flame", "ignite", "infernal"]):
            elem.append("fire")
        if any(k in skill_lower for k in ["lightning", "shock", "spark", "storm"]):
            elem.append("lightning")
        if any(k in skill_lower for k in ["chaos", "poison", "venom"]):
            elem.append("chaos")
        if any(k in skill_lower for k in ["physical", "bleed"]):
            elem.append("physical")
        return elem

    def _infer_damage_type(self, skill: str) -> list[str]:
        """Inferisce damage_type da skill name."""
        skill_lower = skill.lower()
        dtype = []
        if any(k in skill_lower for k in ["strike", "slam", "attack", "melee"]):
            dtype.append("attack")
        if any(k in skill_lower for k in ["nova", "ball", "storm", "spell", "brand"]):
            dtype.append("spell")
        if any(k in skill_lower for k in ["dot", "poison", "burn", "bleed"]):
            dtype.append("dot")
        if any(k in skill_lower for k in ["minion", "zombie", "skeleton", "golem"]):
            dtype.append("minion")
        return dtype
