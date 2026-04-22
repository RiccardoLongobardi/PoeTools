"""FOB: item pricing via official PoE Trade API."""
from __future__ import annotations
import httpx
import asyncio
import logging
from typing import Optional
from statistics import median

logger = logging.getLogger(__name__)

TRADE_SEARCH_URL = "https://www.pathofexile.com/api/trade/search/{league}"
TRADE_FETCH_URL = "https://www.pathofexile.com/api/trade/fetch/{ids}"


class TradePricer:
    """Interface to PoE Trade API for item pricing."""
    
    def __init__(self, league: str = "Settlers", timeout_s: float = 10.0):
        self.league = league
        self.timeout_s = timeout_s
    
    async def estimate_unique_price(self, item_name: str) -> Optional[float]:
        """Estimate unique item price via trade API.
        
        Returns: Price in chaos orbs, or None if not found
        """
        try:
            query = {
                "query": {"name": item_name, "type": "", "status": {"option": "online"}},
                "sort": {"price": "asc"},
            }
            
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                url = TRADE_SEARCH_URL.format(league=self.league)
                resp = await client.post(url, json=query, headers={"User-Agent": "FOB/1.0"})
                
                if resp.status_code != 200:
                    return None
                
                data = resp.json()
                ids = data.get("result", [])[:10]
                if not ids:
                    return None
                
                await asyncio.sleep(1)  # Rate limit
                
                fetch = TRADE_FETCH_URL.format(ids=",".join(ids))
                fetch += f"?query={data.get('id', '')}"
                fetch_resp = await client.get(fetch, headers={"User-Agent": "FOB/1.0"})
                
                if fetch_resp.status_code != 200:
                    return None
                
                listings = fetch_resp.json().get("result", [])
                prices = []
                
                for listing in listings:
                    price = listing.get("listing", {}).get("price", {})
                    amt = price.get("amount")
                    curr = price.get("currency")
                    
                    if curr == "chaos" and amt:
                        prices.append(float(amt))
                    elif curr == "divine" and amt:
                        prices.append(float(amt) * 200)  # 1 div ≈ 200c
                
                if not prices:
                    return None
                
                return median(prices)
                
        except Exception as exc:
            logger.error(f"Pricing error for {item_name}: {exc}")
            return None
    
    async def estimate_build_cost(self, unique_items: list[str]) -> dict:
        """Estimate total build cost.
        
        Returns: Dict with item costs and totals
        """
        costs = {}
        total = 0
        
        for item in unique_items:
            price = await self.estimate_unique_price(item)
            if price:
                costs[item] = price
                total += price
        
        return {
            "items": costs,
            "total_chaos": round(total, 2),
            "total_divine": round(total / 200, 2),
            "league": self.league,
        }


async def estimate_item_cost_trade(item_query: dict, league: str = "Settlers") -> Optional[float]:
    """Helper for compatibility."""
    pricer = TradePricer(league=league)
    return await pricer.estimate_unique_price(item_query.get("name", ""))


# Common uniques by build archetype
COMMON_UNIQUES = {
    "cold_spell": ["Hrimsorrow", "Petrified Blood"],
    "fire_dot": ["Kaom's Heart", "Dyadian Dawn"],
    "lightning_attack": ["Hyaon's Fury", "Starkonja's Head"],
    "physical_melee": ["Abyssus", "Kaom's Roots"],
    "chaos_dot": ["Dendrobate", "Atziri's Step"],
}
