"""FOB: item pricing via official trade API."""

from __future__ import annotations
import httpx
from typing import Optional


async def estimate_item_cost_trade(
    item_query: dict, league: str = "Mirage"
) -> Optional[float]:
    """Estimate item cost using official trade API."""
    # TODO: implement POST /api/trade/search + GET /api/trade/fetch
    return None
