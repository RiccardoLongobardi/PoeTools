"""Test degli endpoint API /api/currencies e /api/snapshots/{trade_id}.

Uso `FastAPI` con solo il router, senza lifespan, così lo scheduler non
parte e i test girano offline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import router
from backend.db import get_session
from backend.models import Currency, ExchangeSnapshot


@pytest.fixture
def api_client(in_memory_db: Any) -> TestClient:
    """FastAPI app con solo il router — niente lifespan, niente scheduler."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_sample_data() -> None:
    """Popola il DB con 2 currency e qualche snapshot per Mirage."""
    now = datetime.now(tz=timezone.utc)
    with get_session() as s:
        divine = Currency(
            trade_id="divine-orb",
            display_name="Divine Orb",
            icon_url="https://example/divine.png",
            category="Currency",
        )
        chaos = Currency(
            trade_id="chaos-orb",
            display_name="Chaos Orb",
            icon_url="https://example/chaos.png",
            category="Currency",
        )
        s.add_all([divine, chaos])
        s.flush()

        # Tre snapshot per divine a 30 min di distanza.
        for i, minutes_ago in enumerate([60, 30, 0]):
            s.add(
                ExchangeSnapshot(
                    currency_id=divine.id,
                    league="Mirage",
                    fetched_at=now - timedelta(minutes=minutes_ago),
                    chaos_equivalent=300.0 + i * 5,  # 300, 305, 310
                    pay_value=1 / (300.0 + i * 5),
                    receive_value=310.0 + i * 5,  # 310, 315, 320
                    pay_listing_count=100 + i,
                    receive_listing_count=80 + i,
                    low_confidence=False,
                )
            )
        # Un solo snapshot per chaos, molto vecchio (fuori dalla finestra 24h).
        s.add(
            ExchangeSnapshot(
                currency_id=chaos.id,
                league="Mirage",
                fetched_at=now - timedelta(days=2),
                chaos_equivalent=1.0,
                pay_value=1.0,
                receive_value=1.0,
                pay_listing_count=500,
                receive_listing_count=500,
                low_confidence=False,
            )
        )


# ---------------------------------------------------------------------------
# /api/currencies
# ---------------------------------------------------------------------------


def test_currencies_returns_all_with_latest_price(api_client: TestClient) -> None:
    _seed_sample_data()
    r = api_client.get("/api/currencies")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2

    divine = next(c for c in data if c["trade_id"] == "divine-orb")
    # L'ultimo snapshot di divine è 310/320.
    assert divine["chaos_equivalent"] == pytest.approx(310.0)
    assert divine["bid_chaos"] == pytest.approx(310.0)
    assert divine["ask_chaos"] == pytest.approx(320.0)
    assert divine["spread_pct"] == pytest.approx(10 / 315 * 100, rel=1e-4)


def test_currencies_filter_by_category(api_client: TestClient) -> None:
    _seed_sample_data()
    # Aggiungo un fragment per testare il filtro.
    with get_session() as s:
        s.add(
            Currency(
                trade_id="sacrifice-at-dusk",
                display_name="Sacrifice at Dusk",
                icon_url=None,
                category="Fragment",
            )
        )

    r = api_client.get("/api/currencies", params={"category": "Fragment"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["trade_id"] == "sacrifice-at-dusk"


def test_currencies_no_snapshot_returns_nulls(api_client: TestClient) -> None:
    """Currency senza snapshot deve tornare last_fetched_at=None, non crash."""
    with get_session() as s:
        s.add(
            Currency(
                trade_id="new-coin",
                display_name="New Coin",
                icon_url=None,
                category="Currency",
            )
        )

    r = api_client.get("/api/currencies")
    assert r.status_code == 200
    new_coin = next(c for c in r.json() if c["trade_id"] == "new-coin")
    assert new_coin["last_fetched_at"] is None
    assert new_coin["chaos_equivalent"] is None


# ---------------------------------------------------------------------------
# /api/snapshots/{trade_id}
# ---------------------------------------------------------------------------


def test_snapshots_returns_points_within_window(api_client: TestClient) -> None:
    _seed_sample_data()
    r = api_client.get("/api/snapshots/divine-orb", params={"hours": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["trade_id"] == "divine-orb"
    assert data["hours"] == 2
    # Tutti e 3 i punti (60/30/0 min ago) cadono nella finestra di 2h.
    assert len(data["points"]) == 3
    # Ordinati ASC per fetched_at.
    ts = [p["fetched_at"] for p in data["points"]]
    assert ts == sorted(ts)


def test_snapshots_window_excludes_old_data(api_client: TestClient) -> None:
    _seed_sample_data()
    # Chaos ha solo 1 snapshot di 2 giorni fa → finestra 24h esclude tutto.
    r = api_client.get("/api/snapshots/chaos-orb", params={"hours": 24})
    assert r.status_code == 200
    assert r.json()["points"] == []


def test_snapshots_unknown_currency_returns_404(api_client: TestClient) -> None:
    r = api_client.get("/api/snapshots/nonexistent-orb")
    assert r.status_code == 404


def test_snapshots_points_include_bid_ask(api_client: TestClient) -> None:
    _seed_sample_data()
    r = api_client.get("/api/snapshots/divine-orb", params={"hours": 2})
    points = r.json()["points"]
    latest = points[-1]
    # Ultimo snapshot: chaos=310, receive=320 → bid=1/(1/310)=310, ask=320
    assert latest["bid_chaos"] == pytest.approx(310.0)
    assert latest["ask_chaos"] == pytest.approx(320.0)


# ---------------------------------------------------------------------------
# /api/health (regression)
# ---------------------------------------------------------------------------


def test_health_still_works(api_client: TestClient) -> None:
    r = api_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
