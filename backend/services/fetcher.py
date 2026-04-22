"""Servizio di fetch: chiama DataSource e persiste risultati su DB.

Due responsabilità distinte:
- `sync_currency_catalog`: aggiorna l'anagrafica (tabella `currency`)
- `fetch_and_store`: scarica uno snapshot e lo scrive (tabella `exchange_snapshot`)
  con dedup intelligente — se i valori non sono cambiati dall'ultima riga,
  non ne scrive una nuova, così non inquiniamo lo storico con righe identiche.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from backend.datasource.base import DataSource, ExchangeQuote
from backend.db import get_session
from backend.models import Currency, ExchangeSnapshot

log = logging.getLogger(__name__)


# Campi che definiscono "uguaglianza economica" tra due snapshot.
# Se tutti coincidono con l'ultimo snapshot a DB, il nuovo fetch è redundante.
_ECON_FIELDS = (
    "chaos_equivalent",
    "pay_value",
    "receive_value",
    "pay_listing_count",
    "receive_listing_count",
    "low_confidence",
)


async def sync_currency_catalog(source: DataSource, league: str) -> int:
    """Aggiorna la tabella `currency` con l'anagrafica corrente.

    Ritorna il numero di righe aggiunte/aggiornate.
    """
    infos = await source.list_currencies(league=league)
    with get_session() as s:
        existing = {c.trade_id: c for c in s.query(Currency).all()}
        count = 0
        for info in infos:
            c = existing.get(info.trade_id)
            if c is None:
                c = Currency(
                    trade_id=info.trade_id,
                    display_name=info.display_name,
                    icon_url=info.icon_url,
                    category=info.category,
                )
                s.add(c)
                count += 1
            else:
                # Aggiorna eventuali campi cambiati (icona nuova, nome rinominato).
                changed = False
                for field in ("display_name", "icon_url", "category"):
                    if getattr(c, field) != getattr(info, field):
                        setattr(c, field, getattr(info, field))
                        changed = True
                if changed:
                    count += 1
        log.info("synced currency catalog: %d added/updated", count)
        return count


def _is_econ_duplicate(last: ExchangeSnapshot, quote: ExchangeQuote) -> bool:
    """True se tutti i campi economici dell'ultimo snapshot coincidono con il quote."""
    for field in _ECON_FIELDS:
        if getattr(last, field) != getattr(quote, field):
            return False
    return True


async def fetch_and_store(source: DataSource, league: str) -> int:
    """Scarica uno snapshot completo e lo scrive in `exchange_snapshot`.

    Dedup: per ogni currency, se l'ultima riga a DB ha gli stessi campi
    economici del nuovo quote, NON scriviamo — sarebbe una riga identica
    a distanza di pochi minuti. Scriviamo solo quando qualcosa è cambiato.

    Ritorna il numero di righe effettivamente scritte (post-dedup).
    """
    quotes = await source.fetch_all(league=league)

    with get_session() as s:
        by_trade_id = {c.trade_id: c for c in s.query(Currency).all()}

        # Pre-carico l'ultimo snapshot di ogni currency della lega, in una
        # sola query. Per ~200 currency è decine di KB — trascurabile, e
        # ci risparmia 200 SELECT separate.
        last_by_currency = _load_last_snapshots(s, league=league)

        written = 0
        skipped_dedup = 0
        for q in quotes:
            currency = by_trade_id.get(q.currency_trade_id)
            if currency is None:
                # Primo fetch: potremmo avere quote per currency non ancora in catalogo.
                # Saltiamo; il prossimo sync_currency_catalog le aggiungerà.
                log.debug("unknown trade_id in quote: %s", q.currency_trade_id)
                continue

            last = last_by_currency.get(currency.id)
            if last is not None and _is_econ_duplicate(last, q):
                skipped_dedup += 1
                continue

            snap = ExchangeSnapshot(
                currency_id=currency.id,
                league=q.league,
                fetched_at=q.fetched_at,
                chaos_equivalent=q.chaos_equivalent,
                pay_value=q.pay_value,
                receive_value=q.receive_value,
                pay_listing_count=q.pay_listing_count,
                receive_listing_count=q.receive_listing_count,
                low_confidence=q.low_confidence,
            )
            s.add(snap)
            written += 1

        log.info(
            "stored %d snapshots for league=%s (dedup skipped %d unchanged)",
            written,
            league,
            skipped_dedup,
        )
        return written


def _load_last_snapshots(
    s, *, league: str
) -> dict[int, ExchangeSnapshot]:
    """Ritorna l'ultimo snapshot per ogni currency della lega, come dict
    {currency_id: ExchangeSnapshot}.

    Implementazione semplice (scan + keep-max-per-group in Python). Per le
    dimensioni in gioco (~200 currency, pochi milioni di snapshot totali nel
    peggior caso) va benissimo — l'indice `ix_snapshot_league_time` fa sì
    che SQLite scansioni solo le righe della lega.
    """
    # Senza ORDER BY sarebbe più veloce, ma così siamo robusti rispetto
    # all'ordine di insert. fetched_at è indicizzato.
    stmt = (
        select(ExchangeSnapshot)
        .where(ExchangeSnapshot.league == league)
        .order_by(ExchangeSnapshot.fetched_at.asc())
    )
    out: dict[int, ExchangeSnapshot] = {}
    for snap in s.execute(stmt).scalars():
        out[snap.currency_id] = snap  # sovrascritta fino all'ultimo (per ASC)
    return out
