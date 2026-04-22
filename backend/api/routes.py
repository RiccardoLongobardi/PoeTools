"""FOB — Frusta Oracle Builder: API routes.

Endpoint esposti:
    POST /fob/oracle    → interpreta query NL, restituisce build + progressione
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.fob_oracle import run_oracle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fob", tags=["oracle"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class OracleRequest(BaseModel):
    query: str
    league: str = "Settlers"


class IntentResult(BaseModel):
    damage_type: list[str] = []
    style: list[str] = []
    budget: str = "any"
    playstyle: list[str] = []
    raw_tokens: list[str] = []


class BuildResult(BaseModel):
    id: str
    name: str
    source: str
    url: Optional[str] = None
    pob_output: Optional[str] = None
    ascendancy: Optional[str] = None
    main_skill: Optional[str] = None
    element: list[str] = []
    damage_type: list[str] = []
    weapon_pref: list[str] = []
    playstyle: list[str] = []
    est_cost_div: Optional[float] = None
    league: Optional[str] = None
    score: float = 0.0


class ProgressionStage(BaseModel):
    phase: str
    level_range: str
    title: str
    main_skill: str
    support_gems: list[str] = []
    key_gear: list[str] = []
    passive_priority: list[str] = []
    notes: str = ""


class PricedItem(BaseModel):
    name: str
    slot: str
    min_chaos: Optional[float] = None
    max_chaos: Optional[float] = None
    avg_chaos: Optional[float] = None
    listings: int = 0


class BuildPlan(BaseModel):
    build_id: str
    league: str
    levelling_stages: list[ProgressionStage] = []
    gear_phases: list[str] = []
    total_cost_div: Optional[float] = None
    priced_items: list[PricedItem] = []
    notes: str = ""


class OracleResponse(BaseModel):
    intent: IntentResult
    builds: list[BuildResult]
    plan: Optional[BuildPlan] = None
    warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/oracle", summary="Query FOB Oracle")             Response, summary="Query FOB Oracle")
async def oracle(req: OracleRequest) -> dict:    """
    Interpreta la query in linguaggio naturale (IT/EN) e restituisce:
    - **intent**: damage type, stile, budget rilevati
    - **builds**: lista di build candidate ordinate per score
    - **plan**: progressione 1→100 con gem setup, gear priority e prezzi PoE Trade
    """
    logger.info("Oracle request: query=%r league=%s", req.query, req.league)
    try:
        result = await run_oracle(req.query, req.league)
        105
        (**result)
    except Exception as exc:
        logger.exception("Oracle error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
