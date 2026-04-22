"""APScheduler wiring — Fase 1 placeholder.

In Fase 1 questo modulo registra un job orario (o ogni N minuti, secondo
`settings.fetch_interval_minutes`) che chiama `services.fetcher.fetch_and_store`.

Per ora, esporta solo `build_scheduler()` così `main.py` ha un handle da
start/stop insieme al backend.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    """Costruisce (ma non fa partire) lo scheduler.

    In Fase 1 aggiungeremo qui `scheduler.add_job(fetch_and_store, ...)`.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")
    log.debug("scheduler built (no jobs registered yet)")
    return scheduler
