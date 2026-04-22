"""FOB: item pricing via poe.ninja itemoverview API."""

from __future__ import annotations
import httpx
from typing import Optional


async def estimate_item_cost_poe_ninja(
    item_name: str, item_type: str, league: str = "Mirage"
) -> Optional[float]:
    """Estimate item cost in divines using poe.ninja itemoverview."""
    url = f"https://poe.ninja/api/data/itemoverview?league={league}&type={item_type}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            for line in data.get("lines", []):
                if line.get("name") == item_name:
                    return line.get("divineValue") or line.get("chaosValue", 0) / 200.0
        except Exception:
            pass
    
    return None
