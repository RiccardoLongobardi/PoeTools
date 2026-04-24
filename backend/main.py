"""FOB — Frusta Oracle Builder
FastAPI entry point.

Avvio:
    uv run uvicorn backend.main:app --reload
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router as fob_router
from backend.api.admin_routes import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FOB — Frusta Oracle Builder",
    description=(
        "Build planner AI per Path of Exile 1. "
        "Interpreta richieste in linguaggio naturale (IT/EN), "
        "suggerisce build da poe.ninja e genera progressione 1→100 "
        "con costi reali via PoE Trade."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fob_router)
app.include_router(admin_router)

# Serve frontend statico da /app
_frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
if _frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "fob-frusta-oracle-builder"}
