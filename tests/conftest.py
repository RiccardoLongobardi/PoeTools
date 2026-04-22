"""Pytest fixtures condivisi."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def currency_overview_sample() -> dict:
    """Risposta di esempio di poe.ninja /currencyoverview?type=Currency&league=Mirage.

    Shape fedele alla documentazione community. Usa numeri plausibili per
    Mirage 3.28 ma non è un dump reale.
    """
    path = FIXTURES / "currencyoverview_mirage_sample.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def fragment_overview_sample() -> dict:
    """Risposta di esempio per type=Fragment."""
    path = FIXTURES / "fragmentoverview_mirage_sample.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def mock_httpx_client(
    currency_overview_sample: dict, fragment_overview_sample: dict
) -> httpx.AsyncClient:
    """AsyncClient httpx con MockTransport che risponde agli endpoint poe.ninja.

    Route:
      GET /currencyoverview?league=*&type=Currency  → currency_overview_sample
      GET /currencyoverview?league=*&type=Fragment  → fragment_overview_sample
    Altri path rispondono 404.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/currencyoverview"):
            ep_type = request.url.params.get("type")
            if ep_type == "Currency":
                return httpx.Response(200, json=currency_overview_sample)
            if ep_type == "Fragment":
                return httpx.Response(200, json=fragment_overview_sample)
        return httpx.Response(404, json={"error": "unknown"})

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="https://poe.ninja/api/data")


# ---------------------------------------------------------------------------
# DB fixture: SQLite in-memory, isolato per test.
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Sostituisce l'engine globale con un SQLite in-memory fresco.

    Tests che toccano il DB devono dipendere da questa fixture. Ogni test
    parte con schema vuoto e viene distrutto a fine test — nessun leak.

    Ritorna l'engine, utile se un test vuole ispezionare direttamente.
    """
    # Import lazy: importiamo qui così il monkey-patch avviene prima che
    # altri moduli usino `engine`/`SessionLocal`.
    from backend import db as db_mod
    from backend import models  # noqa: F401 — registra i modelli su Base

    # StaticPool: tutte le sessioni condividono la STESSA connessione sqlite.
    # Senza questo, ogni connessione aprirebbe un :memory: proprio (= vuoto),
    # e il threadpool di FastAPI vedrebbe tabelle inesistenti.
    test_engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)

    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", TestSession)

    db_mod.Base.metadata.create_all(bind=test_engine)

    try:
        yield test_engine
    finally:
        test_engine.dispose()
