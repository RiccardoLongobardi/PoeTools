"""Cache store: lettura/scrittura builds_cache.<league>.json su disco."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)


def _cache_path(league: str) -> Path:
    return DATA_DIR / f"builds_cache.{league.lower()}.json"


def load_cache(league: str) -> dict:
    path = _cache_path(league)
    if not path.exists():
        return _empty_cache(league)
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Cache load failed (%s), returning empty: %s", path, exc)
        return _empty_cache(league)


def save_cache(league: str, data: dict) -> None:
    path = _cache_path(league)
    data["last_refresh_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Cache saved: %s (%d builds)", path.name, len(data.get("builds", [])))


def cache_status(league: str) -> dict:
    data = load_cache(league)
    return {
        "league": league,
        "last_refresh_at": data.get("last_refresh_at"),
        "total_builds": len(data.get("builds", [])),
        "sources": data.get("sources", {}),
    }


def _empty_cache(league: str) -> dict:
    return {
        "cache_version": 1,
        "league": league,
        "last_refresh_at": None,
        "sources": {
            "ladder": {"status": "never", "count": 0, "updated_at": None, "error": None},
            "pobbin": {"status": "never", "count": 0, "updated_at": None, "error": None},
            "maxroll": {"status": "never", "count": 0, "updated_at": None, "error": None},
            "mobalytics": {"status": "skipped", "count": 0, "updated_at": None, "error": None},
        },
        "builds": [],
    }
