"""Entry point del backend — CLI Typer + bootstrap FastAPI.

Comandi disponibili:

    faustus init-db                 # crea schema SQLite
    faustus fetch-once [--league X] # fa un fetch sincrono e scrive a DB
    faustus preview [--league X]    # fetch senza scrittura, stampa top N
    faustus stats [--league X]      # statistiche sullo storico accumulato
    faustus arb   [--league X]      # top arbitrage opportunities da ultimo snapshot
    faustus serve                   # avvia API FastAPI + scheduler ogni 15min
    faustus desktop                 # fase 4: bundle PyWebView (stub)

`serve` avvia anche l'APScheduler che rifa il fetch ogni
`FAUSTUS_FETCH_INTERVAL_MINUTES` minuti (default 15) — così se il backend
gira in background ti costruisce lo storico da solo.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import typer
import uvicorn
from fastapi import FastAPI
from rich.console import Console
from rich.table import Table

# Windows-friendly: forza stdout/stderr a UTF-8 così le tabelle Rich (che
# usano caratteri Unicode come → ┏ ┡) non rompono quando si redireziona
# l'output a un file con la console cp1252 di default.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — best-effort, non fatale
            pass

from backend import __version__
from backend.api.routes import router as api_router
from backend.config import settings
from backend.datasource import PoeNinjaSource
from backend.db import init_db as _init_db
from backend.services.fetcher import fetch_and_store, sync_currency_catalog
from backend.services.scheduler import (
    run_fetch_now,
    start_scheduler,
    stop_scheduler,
)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

cli = typer.Typer(
    name="faustus",
    help=f"{settings.app_name} — CLI v{__version__}",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


# -----------------------------------------------------------------------------
# FastAPI app factory
# -----------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle hooks dell'app FastAPI.

    Startup: crea schema se manca, lancia un fetch immediato, avvia lo scheduler.
    Shutdown: ferma lo scheduler (che chiude anche l'httpx client).
    """
    _init_db()
    # Fetch immediato per non aspettare il 1° tick (default 15 min).
    # Se fallisce (poe.ninja down), log e continua: lo scheduler riproverà.
    try:
        n = await run_fetch_now()
        logging.getLogger(__name__).info("bootstrap fetch: %d new snapshots", n)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("bootstrap fetch failed (non-fatal)")
    start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=_lifespan,
        # CORS lo aggiungeremo in Fase 3 quando Vite dev server (5173)
        # parlerà col backend (8765).
    )
    app.include_router(api_router)
    return app


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------


@cli.command("init-db")
def cmd_init_db() -> None:
    """Crea lo schema SQLite (idempotente)."""
    _init_db()
    console.print(f"[green]OK[/] schema creato in [bold]{settings.db_url}[/]")


@cli.command("fetch-once")
def cmd_fetch_once(
    league: str = typer.Option(settings.league, "--league", "-l"),
    also_catalog: bool = typer.Option(
        True, "--catalog/--no-catalog", help="Aggiorna anche l'anagrafica currency."
    ),
) -> None:
    """Fa un fetch sincrono e scrive a DB. Utile per debug."""

    async def _run() -> None:
        _init_db()
        source = PoeNinjaSource()
        try:
            if also_catalog:
                console.print(f"Syncing currency catalog for [cyan]{league}[/]...")
                n = await sync_currency_catalog(source, league=league)
                console.print(f"  → {n} currencies added/updated")

            console.print(f"Fetching market snapshot for [cyan]{league}[/]...")
            n = await fetch_and_store(source, league=league)
            console.print(f"  → {n} snapshots written")
        finally:
            await source.aclose()

    asyncio.run(_run())


@cli.command("preview")
def cmd_preview(
    league: str = typer.Option(settings.league, "--league", "-l"),
    limit: int = typer.Option(15, "--limit", "-n"),
) -> None:
    """Stampa le top-N currency per chaos equivalent, senza scrivere a DB.

    Utile per "vedo se funziona" senza inquinare il DB in early dev.
    """

    async def _run() -> None:
        source = PoeNinjaSource()
        try:
            quotes = await source.fetch_currency_overview(league=league)
        finally:
            await source.aclose()

        quotes.sort(key=lambda q: q.chaos_equivalent, reverse=True)

        table = Table(title=f"Top {limit} currencies — {league}")
        table.add_column("trade_id", style="cyan")
        table.add_column("chaos eq", justify="right", style="green")
        table.add_column("pay", justify="right")
        table.add_column("receive", justify="right")
        table.add_column("listings", justify="right")
        table.add_column("low?", justify="center")

        for q in quotes[:limit]:
            # `.4g` = 4 significant figures, utile perché pay può essere 0.003
            # (reciproco) e receive 322.70 (prezzo diretto).
            table.add_row(
                q.currency_trade_id,
                f"{q.chaos_equivalent:,.2f}",
                f"{q.pay_value:.4g}" if q.pay_value else "-",
                f"{q.receive_value:.4g}" if q.receive_value else "-",
                str((q.pay_listing_count or 0) + (q.receive_listing_count or 0)),
                "!" if q.low_confidence else "",
            )
        console.print(table)

    asyncio.run(_run())


@cli.command("serve")
def cmd_serve(
    host: str = typer.Option(settings.api_host, "--host"),
    port: int = typer.Option(settings.api_port, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Avvia il backend FastAPI."""
    console.print(f"Starting API on [bold]http://{host}:{port}[/]")
    uvicorn.run(
        "backend.main:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@cli.command("stats")
def cmd_stats(
    league: str = typer.Option(settings.league, "--league", "-l"),
) -> None:
    """Statistiche sullo storico accumulato per la lega.

    Utile per rispondere a "ho già abbastanza dati per il grafico a 24h?".
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from backend.db import get_session
    from backend.models import Currency, ExchangeSnapshot

    _init_db()

    with get_session() as s:
        total = s.execute(
            select(func.count()).select_from(ExchangeSnapshot).where(
                ExchangeSnapshot.league == league
            )
        ).scalar_one()

        distinct_currencies = s.execute(
            select(func.count(func.distinct(ExchangeSnapshot.currency_id))).where(
                ExchangeSnapshot.league == league
            )
        ).scalar_one()

        oldest = s.execute(
            select(func.min(ExchangeSnapshot.fetched_at)).where(
                ExchangeSnapshot.league == league
            )
        ).scalar_one()

        newest = s.execute(
            select(func.max(ExchangeSnapshot.fetched_at)).where(
                ExchangeSnapshot.league == league
            )
        ).scalar_one()

        cutoff_24h = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        last_24h = s.execute(
            select(func.count()).select_from(ExchangeSnapshot).where(
                ExchangeSnapshot.league == league,
                ExchangeSnapshot.fetched_at >= cutoff_24h,
            )
        ).scalar_one()

        low_conf = s.execute(
            select(func.count()).select_from(ExchangeSnapshot).where(
                ExchangeSnapshot.league == league,
                ExchangeSnapshot.low_confidence.is_(True),
            )
        ).scalar_one()

        catalog_size = s.execute(select(func.count()).select_from(Currency)).scalar_one()

    table = Table(title=f"Stats — {league}")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right")

    span = "—"
    if oldest and newest:
        delta = newest - oldest
        hours = delta.total_seconds() / 3600
        span = f"{hours:.1f}h ({delta.days}d)"

    low_conf_pct = (low_conf / total * 100) if total else 0

    table.add_row("catalog currencies", f"{catalog_size:,}")
    table.add_row("total snapshots", f"{total:,}")
    table.add_row("distinct currencies tracked", f"{distinct_currencies:,}")
    table.add_row("oldest snapshot", str(oldest) if oldest else "—")
    table.add_row("newest snapshot", str(newest) if newest else "—")
    table.add_row("history span", span)
    table.add_row("snapshots in last 24h", f"{last_24h:,}")
    table.add_row("low-confidence ratio", f"{low_conf_pct:.1f}%")

    console.print(table)


@cli.command("arb")
def cmd_arb(
    league: str = typer.Option(settings.league, "--league", "-l"),
    min_profit: float = typer.Option(
        1.0, "--min-profit", "-p",
        help="Soglia di profit% per segnalare una opportunità.",
    ),
    min_listings: int = typer.Option(
        5, "--min-listings",
        help="Soglia di liquidità (listing count minimo su entrambi i lati).",
    ),
    max_spread: float = typer.Option(
        30.0, "--max-spread",
        help="Esclude currency con spread interno sopra soglia (%). "
             "Usa 999 per disattivare.",
    ),
    limit: int = typer.Option(
        20, "--limit", "-n",
        help="Numero massimo di righe per tabella.",
    ),
    mode: str = typer.Option(
        "both", "--mode", "-m",
        help="cycles | pairs | both",
    ),
) -> None:
    """Stampa le top arbitrage opportunities dall'ultimo snapshot.

    Non fa fetch: usa i dati già a DB. Fai prima `faustus fetch-once`
    (o lascia girare `faustus serve`) per avere dati freschi.
    """
    from backend.services.arbitrage import (
        find_cycles,
        find_pair_opportunities,
        get_latest_prices,
    )

    if mode not in ("cycles", "pairs", "both"):
        console.print(f"[red]invalid --mode:[/] {mode!r}. Use cycles|pairs|both.")
        raise typer.Exit(code=2)

    _init_db()
    prices = get_latest_prices(league=league)
    if not prices:
        console.print(
            f"[yellow]Nessun prezzo a DB per lega [bold]{league}[/]. "
            f"Esegui prima [cyan]faustus fetch-once -l {league}[/]."
        )
        raise typer.Exit(code=1)

    # Convenzione UX: --max-spread 999+ = filtro disattivato
    effective_max_spread: float | None = max_spread if max_spread < 999 else None

    console.print(
        f"Computing arbitrage on [cyan]{len(prices)}[/] currencies — "
        f"min_profit={min_profit}%, min_listings={min_listings}, "
        f"max_spread={effective_max_spread if effective_max_spread is not None else 'off'}"
    )

    if mode in ("cycles", "both"):
        cycles = find_cycles(
            prices,
            min_profit_pct=min_profit,
            min_listing_count=min_listings,
            max_spread_pct=effective_max_spread,
        )
        t = Table(title=f"Arbitrage cycles — {league} (top {limit})")
        t.add_column("#", style="dim", justify="right")
        t.add_column("profit %", justify="right", style="green")
        t.add_column("hops", justify="right")
        t.add_column("min listings", justify="right")
        t.add_column("path", style="cyan")
        t.add_column("low?", justify="center")

        for i, c in enumerate(cycles[:limit], 1):
            t.add_row(
                str(i),
                f"{c.profit_pct:+.2f}",
                str(c.length),
                str(c.min_listing_count),
                " → ".join(c.path),
                "!" if c.low_confidence else "",
            )
        if not cycles:
            t.add_row("—", "—", "—", "—", "[dim]nessun ciclo sopra soglia[/]", "")
        console.print(t)

    if mode in ("pairs", "both"):
        pairs = find_pair_opportunities(
            prices,
            min_profit_pct=min_profit,
            min_listing_count=min_listings,
            max_spread_pct=effective_max_spread,
        )
        t = Table(title=f"Mid-vs-spread pairs — {league} (top {limit})")
        t.add_column("#", style="dim", justify="right")
        t.add_column("profit %", justify="right", style="green")
        t.add_column("A → B", style="cyan")
        t.add_column("Faustus rate", justify="right")
        t.add_column("market rate", justify="right")
        t.add_column("spread A/B %", justify="right", style="yellow")
        t.add_column("min listings", justify="right")
        t.add_column("low?", justify="center")

        for i, p in enumerate(pairs[:limit], 1):
            t.add_row(
                str(i),
                f"{p.profit_pct:+.2f}",
                f"{p.source_trade_id} → {p.target_trade_id}",
                f"{p.faustus_rate:.4g}",
                f"{p.market_rate:.4g}",
                f"{p.source_spread_pct:.1f}/{p.target_spread_pct:.1f}",
                str(p.min_listing_count),
                "!" if p.low_confidence else "",
            )
        if not pairs:
            t.add_row("—", "—", "[dim]nessuna coppia sopra soglia[/]", "—", "—", "—", "—", "")
        console.print(t)


@cli.command("desktop")
def cmd_desktop() -> None:
    """Fase 4 — bundle PyWebView. Non ancora implementato."""
    console.print(
        "[yellow]not implemented yet.[/] Arriva in Fase 4 (packaging desktop)."
    )
    raise typer.Exit(code=1)


if __name__ == "__main__":
    cli()
