"""Test della logica di dedup di fetch_and_store.

Verifichiamo che:
- Il primo fetch scrive tutte le righe.
- Un secondo fetch con DATI IDENTICI scrive 0 righe (dedup).
- Un fetch con DATI MODIFICATI scrive solo le currency cambiate.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import httpx
import pytest

from backend.datasource.poe_ninja import PoeNinjaSource
from backend.db import get_session
from backend.models import Currency, ExchangeSnapshot
from backend.services.fetcher import fetch_and_store, sync_currency_catalog


def _make_client_for(
    currency_payload: dict, fragment_payload: dict
) -> httpx.AsyncClient:
    """AsyncClient con MockTransport che risponde con i payload forniti."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/currencyoverview"):
            ep_type = request.url.params.get("type")
            if ep_type == "Currency":
                return httpx.Response(200, json=currency_payload)
            if ep_type == "Fragment":
                return httpx.Response(200, json=fragment_payload)
        return httpx.Response(404, json={"error": "unknown"})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://poe.ninja/api/data",
    )


async def test_first_fetch_writes_all(
    in_memory_db: Any,
    currency_overview_sample: dict,
    fragment_overview_sample: dict,
) -> None:
    client = _make_client_for(currency_overview_sample, fragment_overview_sample)
    src = PoeNinjaSource(client=client)
    try:
        await sync_currency_catalog(src, league="Mirage")
        written = await fetch_and_store(src, league="Mirage")
    finally:
        await src.aclose()

    # 5 currency + 2 fragment = 7 righe attese al primo fetch.
    assert written == 7
    with get_session() as s:
        assert s.query(ExchangeSnapshot).count() == 7


async def test_second_identical_fetch_writes_zero(
    in_memory_db: Any,
    currency_overview_sample: dict,
    fragment_overview_sample: dict,
) -> None:
    """Fetching gli stessi dati due volte deve produrre 0 inserimenti al 2°."""
    client = _make_client_for(currency_overview_sample, fragment_overview_sample)
    src = PoeNinjaSource(client=client)
    try:
        await sync_currency_catalog(src, league="Mirage")
        first = await fetch_and_store(src, league="Mirage")
        second = await fetch_and_store(src, league="Mirage")
    finally:
        await src.aclose()

    assert first == 7
    assert second == 0, "dedup deve aver saltato TUTTE le righe identiche"

    with get_session() as s:
        # Il totale è ancora 7 — il 2° fetch non ha aggiunto nulla.
        assert s.query(ExchangeSnapshot).count() == 7


async def test_fetch_writes_only_changed_currencies(
    in_memory_db: Any,
    currency_overview_sample: dict,
    fragment_overview_sample: dict,
) -> None:
    """Quando 1 sola currency cambia prezzo, scriviamo 1 sola nuova riga."""
    # Primo fetch: 7 righe.
    client_1 = _make_client_for(currency_overview_sample, fragment_overview_sample)
    src_1 = PoeNinjaSource(client=client_1)
    try:
        await sync_currency_catalog(src_1, league="Mirage")
        await fetch_and_store(src_1, league="Mirage")
    finally:
        await src_1.aclose()

    # Modifico il prezzo di Divine Orb e rifetch.
    modified = deepcopy(currency_overview_sample)
    for line in modified["lines"]:
        if line["detailsId"] == "divine-orb":
            line["chaosEquivalent"] = 999.0  # cambiato
            break

    client_2 = _make_client_for(modified, fragment_overview_sample)
    src_2 = PoeNinjaSource(client=client_2)
    try:
        written = await fetch_and_store(src_2, league="Mirage")
    finally:
        await src_2.aclose()

    assert written == 1, "solo divine-orb è cambiato, dedup deve saltare gli altri 6"

    with get_session() as s:
        # Ora abbiamo 7 + 1 = 8 snapshot totali.
        assert s.query(ExchangeSnapshot).count() == 8
        # E il divine-orb deve avere 2 snapshot a DB: quello vecchio + quello nuovo.
        divine = s.query(Currency).filter_by(trade_id="divine-orb").one()
        divine_snaps = (
            s.query(ExchangeSnapshot).filter_by(currency_id=divine.id).all()
        )
        assert len(divine_snaps) == 2
        assert {s.chaos_equivalent for s in divine_snaps} == {222.75, 999.0}


async def test_dedup_detects_listing_count_changes(
    in_memory_db: Any,
    currency_overview_sample: dict,
    fragment_overview_sample: dict,
) -> None:
    """Anche un cambio di listing_count (= volume) vale come 'cambiato'.

    Il prezzo può essere stabile ma il volume informa sulla liquidità:
    non possiamo deduplicare solo sul prezzo.
    """
    client_1 = _make_client_for(currency_overview_sample, fragment_overview_sample)
    src_1 = PoeNinjaSource(client=client_1)
    try:
        await sync_currency_catalog(src_1, league="Mirage")
        await fetch_and_store(src_1, league="Mirage")
    finally:
        await src_1.aclose()

    modified = deepcopy(currency_overview_sample)
    for line in modified["lines"]:
        if line["detailsId"] == "chaos-orb":
            # Prezzo identico, ma listing count diverso.
            line["pay"]["listing_count"] = 999
            break

    client_2 = _make_client_for(modified, fragment_overview_sample)
    src_2 = PoeNinjaSource(client=client_2)
    try:
        written = await fetch_and_store(src_2, league="Mirage")
    finally:
        await src_2.aclose()

    assert written == 1
