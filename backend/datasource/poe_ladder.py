"""PoE Ladder API - fetch real builds from official PathOfExile.com API."""
from __future__ import annotations
import httpx
import logging
from typing import Optional
from backend.services.fob_oracle import Build, BuildQuery

logger = logging.getLogger(__name__)


class PoELadderSource:
    """Fetch builds from official PoE ladder API."""
    
    def __init__(
        self,
        league: str = "Mirage",
        base_url: str = "https://www.pathofexile.com/api",
        timeout_s: float = 10.0,
    ):
        self.league = league
        self.base_url = base_url
        self.timeout_s = timeout_s
    
    async def fetch_builds(self, query: BuildQuery, limit: int = 50) -> list[Build]:
        """Fetch top builds from PoE official ladder API.
        
        Returns:
            List of Build objects with real ladder data
        """
        url = f"{self.base_url}/ladders/{self.league}"
        logger.info("Fetching ladder from %s (limit=%d)", url, limit)
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(url, params={"limit": limit})
                resp.raise_for_status()
                
                data = resp.json()
                entries = data.get("entries", [])
                
                if not entries:
                    logger.warning("No ladder entries found for league: %s", self.league)
                    return []
                
                builds = []
                for i, entry in enumerate(entries[:limit]):
                    build = self._parse_ladder_entry(entry, i)
                    if build:
                        builds.append(build)
                
                logger.info("Fetched %d builds from ladder", len(builds))
                return builds
                
        except httpx.HTTPError as exc:
            logger.error(f"Ladder fetch failed: {exc}")
            return []
    
    def _parse_ladder_entry(self, entry: dict, index: int) -> Optional[Build]:
        """Parse a ladder entry into a Build object."""
        try:
            character = entry.get("character", {})
            account = entry.get("account", {})
            
            char_name = character.get("name", f"Character_{index}")
            char_class = character.get("class", "Unknown")
            level = character.get("level", 1)
            
            # Infer ascendancy from class name
            ascendancy = self._map_class_to_ascendancy(char_class)
            
            # Infer tags from class (basic heuristics)
            element = self._infer_element_from_class(char_class)
            damage_type = self._infer_damage_type_from_class(char_class)
            
            return Build(
                id=f"ladder_{self.league}_{index}",
                name=f"{char_name} ({char_class})",
                source="poe_ladder",
                ascendancy=ascendancy,
                main_skill="Unknown",  # API doesn't provide this
                element=element,
                damage_type=damage_type,
                league=self.league,
                est_cost_div=None,  # Unknown from ladder
            )
            
        except Exception as exc:
            logger.error(f"Failed to parse ladder entry: {exc}")
            return None
    
    def _map_class_to_ascendancy(self, char_class: str) -> str:
        """Map character class to a common ascendancy."""
        class_map = {
            "Witch": "Necromancer",
            "Shadow": "Trickster",
            "Ranger": "Raider",
            "Duelist": "Slayer",
            "Marauder": "Juggernaut",
            "Templar": "Inquisitor",
            "Scion": "Ascendant",
        }
        return class_map.get(char_class, char_class)
    
    def _infer_element_from_class(self, char_class: str) -> list[str]:
        """Infer element from character class (rough heuristic)."""
        element_map = {
            "Witch": ["cold", "chaos"],
            "Templar": ["fire", "lightning"],
            "Shadow": ["chaos", "physical"],
            "Ranger": ["cold", "lightning"],
            "Duelist": ["physical"],
            "Marauder": ["fire", "physical"],
            "Scion": ["physical"],
        }
        return element_map.get(char_class, ["physical"])
    
    def _infer_damage_type_from_class(self, char_class: str) -> list[str]:
        """Infer damage type from class."""
        damage_map = {
            "Witch": ["spell"],
            "Templar": ["spell"],
            "Shadow": ["spell", "attack"],
            "Ranger": ["attack"],
            "Duelist": ["attack"],
            "Marauder": ["attack"],
            "Scion": ["attack", "spell"],
        }
        return damage_map.get(char_class, ["attack"])