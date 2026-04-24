"""Admin routes: refresh cache, status, force-refresh per source.

Protezione: HTTP Basic Auth con credenziali da env (default: admin/fob).
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Optional

from backend.services.refresh_service import refresh_cache
from backend.services.cache_store import cache_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fob/admin", tags=["admin"])
security = HTTPBasic()

ADMIN_USER = os.getenv("FOB_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("FOB_ADMIN_PASS", "fob")


def _require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    ok_user = secrets.compare_digest(creds.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), ADMIN_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali admin errate",
            headers={"WWW-Authenticate": "Basic"},
        )


class RefreshRequest(BaseModel):
    league: str = "Mirage"
    sources: Optional[list[str]] = None  # None = tutte
    limit_per_source: int = 100


_refresh_status: dict = {"running": False, "last_report": None}


async def _run_refresh(league: str, sources: Optional[list[str]], limit: int) -> None:
    global _refresh_status
    _refresh_status["running"] = True
    try:
        report = await refresh_cache(league=league, sources=sources, limit_per_source=limit)
        _refresh_status["last_report"] = report
    except Exception as exc:
        _refresh_status["last_report"] = {"error": str(exc)}
    finally:
        _refresh_status["running"] = False


@router.post("/refresh", summary="Avvia refresh cache (background)")
async def trigger_refresh(
    req: RefreshRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_admin),
) -> dict:
    if _refresh_status["running"]:
        return {"status": "already_running", "message": "Refresh già in corso"}
    background_tasks.add_task(_run_refresh, req.league, req.sources, req.limit_per_source)
    return {"status": "started", "league": req.league, "sources": req.sources or "all"}


@router.get("/refresh/status", summary="Stato ultimo refresh")
async def refresh_status_endpoint(_: None = Depends(_require_admin)) -> dict:
    return {
        "running": _refresh_status["running"],
        "last_report": _refresh_status["last_report"],
    }


@router.get("/cache/status", summary="Stato cache per league")
async def get_cache_status(
    league: str = "Mirage",
    _: None = Depends(_require_admin),
) -> dict:
    return cache_status(league)
