"""Scheduler periodico per il fetch di poe.ninja.

Girato dentro l'event loop di FastAPI via `AsyncIOScheduler`. Parte dal
lifespan dell'app (vedi `backend.main.create_app`) e si ferma al shutdown.

Design:
- Una singola istanza globale, creata on-demand con `get_scheduler()`.
- Una sola job attiva per (lega), così cambiando lega via API non
  accumuliamo job vecchi.
- Il fetch è idempotente rispetto al DB (dedup in fetch_and_store),
  quindi se due job si sovrappongono non è un disastro — ma comunque
  APScheduler gestisce `max_instances=1` per evitarlo.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import settings
from backend.datasource.poe_ninja import PoeNinjaSource
from backend.services.fetcher import fetch_and_store, sync_currency_catalog

log = logging.getLogger(__name__)


_scheduler: AsyncIOScheduler | None = None
# Il DataSource è condiviso tra tutte le invocazioni di job, così
# l'AsyncClient httpx riusa le connessioni (keep-alive).
_source: PoeNinjaSource | None = None


async def _run_fetch_cycle(league: str) -> None:
    """Un ciclo completo: sync catalogo + fetch_and_store.

    Catturiamo le eccezioni qui: se il fetch fallisce, NON vogliamo che lo
    scheduler si fermi — deve riprovare al prossimo tick.
    """
    global _source
    if _source is None:
        _source = PoeNinjaSource()
    try:
        await sync_currency_catalog(_source, league=league)
        n = await fetch_and_store(_source, league=league)
        log.info("scheduled fetch done: %d new snapshots for league=%s", n, league)
    except Exception:  # noqa: BLE001 — log e continua, niente crash
        log.exception("scheduled fetch failed for league=%s", league)


def get_scheduler() -> AsyncIOScheduler:
    """Ritorna lo scheduler globale, creandolo al primo accesso."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler(league: str | None = None) -> None:
    """Avvia lo scheduler e registra il job di fetch periodico.

    Idempotente: se già partito, non fa nulla.
    """
    sched = get_scheduler()
    lg = league or settings.league

    # Rimuovi eventuali job precedenti per la stessa lega (cambio lega runtime).
    for job in list(sched.get_jobs()):
        if job.id == f"fetch-{lg}":
            sched.remove_job(job.id)

    sched.add_job(
        _run_fetch_cycle,
        trigger=IntervalTrigger(minutes=settings.fetch_interval_minutes),
        kwargs={"league": lg},
        id=f"fetch-{lg}",
        name=f"poe.ninja fetch ({lg})",
        max_instances=1,  # no overlap se un tick è lento
        coalesce=True,  # se siamo dormiti, esegui 1 sola volta non N
        # Primo tick immediato (next_run_time=now) lo otteniamo con run_once all'avvio,
        # cfr. create_app lifespan. APScheduler di default aspetta il 1° intervallo.
    )

    if not sched.running:
        sched.start()
    log.info(
        "scheduler started: fetch every %d min for league=%s",
        settings.fetch_interval_minutes,
        lg,
    )


async def stop_scheduler() -> None:
    """Ferma lo scheduler e chiude il data source condiviso.

    Async perché `DataSource.aclose()` è async — vogliamo aspettare che
    l'httpx client rilasci le connessioni prima di lasciar morire il loop.
    """
    global _source
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
    if _source is not None:
        await _source.aclose()
        _source = None
    log.info("scheduler stopped")


async def run_fetch_now(league: str | None = None) -> int:
    """Esegue un fetch immediato fuori dallo schedule (trigger manuale).

    Usato al bootstrap dell'app per non aspettare `fetch_interval_minutes`
    prima del primo dato, e come endpoint API "refresh now" in futuro.
    """
    global _source
    lg = league or settings.league
    if _source is None:
        _source = PoeNinjaSource()
    await sync_currency_catalog(_source, league=lg)
    return await fetch_and_store(_source, league=lg)
