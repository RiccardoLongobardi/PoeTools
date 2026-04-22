"""Routes FastAPI.

Fase 1 espone i primi endpoint "dati" che il frontend consumerà:

    GET  /api/health              liveness
    GET  /api/currencies          lista currency + ultimo prezzo
    GET  /api/snapshots/{trade_id}?hours=24   time-series per grafico
    POST /api/fetch/trigger       forza un fetch immediato

Schema-wise: le response sono Pydantic models, così FastAPI genera OpenAPI
e il frontend può fare type-gen (Phase 3).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select

from backend import __version__
from backend.config import settings
from backend.db import get_session
from backend.models import Currency, ExchangeSnapshot
from backend.services.arbitrage import (
    get_latest_prices,
    find_cycles,
    find_pair_opportunities,
)
from backend.services.scheduler import run_fetch_now

router = APIRouter(prefix="/api", tags=["system"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CurrencySummary(BaseModel):
    """Una currency con il suo ultimo prezzo noto."""

    trade_id: str
    display_name: str
    icon_url: str | None
    category: str

    # Ultimo snapshot — può essere None se la currency esiste in catalogo
    # ma non abbiamo ancora un fetch per lei.
    last_fetched_at: datetime | None = None
    chaos_equivalent: float | None = None
    bid_chaos: float | None = None
    ask_chaos: float | None = None
    spread_pct: float | None = None
    low_confidence: bool = False

    model_config = ConfigDict(from_attributes=False)


class SnapshotPoint(BaseModel):
    """Un punto della time-series di prezzo."""

    fetched_at: datetime
    chaos_equivalent: float
    bid_chaos: float | None
    ask_chaos: float | None
    pay_listing_count: int | None
    receive_listing_count: int | None
    low_confidence: bool


class SnapshotSeries(BaseModel):
    """Serie temporale completa per una currency."""

    trade_id: str
    display_name: str
    league: str
    hours: int
    points: list[SnapshotPoint]


class FetchTriggerResult(BaseModel):
    written: int
    league: str


class ArbitrageCycleOut(BaseModel):
    """Ciclo di arbitrage rilevato da Bellman-Ford."""

    path: list[str]
    profit_pct: float
    min_listing_count: int
    low_confidence: bool
    step_rates: list[float]


class ArbitragePairOut(BaseModel):
    """Opportunità mid-vs-spread su una coppia."""

    source_trade_id: str
    target_trade_id: str
    faustus_rate: float
    market_rate: float
    profit_pct: float
    min_listing_count: int
    low_confidence: bool
    source_spread_pct: float
    target_spread_pct: float


class ArbitrageResult(BaseModel):
    """Response di /api/arbitrage.

    `cycles` e `pairs` possono essere vuote se `mode` non le ha richieste
    o se nessuna opportunità soddisfa le soglie.
    """

    league: str
    mode: str
    min_profit_pct: float
    min_listing_count: int
    max_spread_pct: float | None
    cycles: list[ArbitrageCycleOut]
    pairs: list[ArbitragePairOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bid_from(pay_value: float | None) -> float | None:
    if not pay_value:
        return None
    return 1.0 / pay_value


def _spread_pct(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2.0
    if mid == 0:
        return None
    return abs(ask - bid) / mid * 100.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, object]:
    """Liveness check. Usato dal frontend per capire se backend è up."""
    return {
        "status": "ok",
        "version": __version__,
        "app": settings.app_name,
        "league": settings.league,
    }


@router.get("/currencies", response_model=list[CurrencySummary])
def list_currencies_endpoint(
    league: str = Query(default=None),
    category: str | None = Query(default=None, description="Filtra per 'Currency' o 'Fragment'"),
) -> list[CurrencySummary]:
    """Lista di tutte le currency con l'ultimo prezzo noto.

    Join naïve: per ~200 currency è trascurabile. Se diventa lento,
    si può fare con un window function in SQL, ma non ora.
    """
    lg = league or settings.league
    out: list[CurrencySummary] = []

    with get_session() as s:
        q = select(Currency)
        if category:
            q = q.where(Currency.category == category)
        currencies = s.execute(q.order_by(Currency.category, Currency.display_name)).scalars().all()

        # Per ogni currency, ultimo snapshot della lega.
        for c in currencies:
            last = s.execute(
                select(ExchangeSnapshot)
                .where(
                    ExchangeSnapshot.currency_id == c.id,
                    ExchangeSnapshot.league == lg,
                )
                .order_by(desc(ExchangeSnapshot.fetched_at))
                .limit(1)
            ).scalar_one_or_none()

            summary = CurrencySummary(
                trade_id=c.trade_id,
                display_name=c.display_name,
                icon_url=c.icon_url,
                category=c.category,
            )
            if last is not None:
                bid = _bid_from(last.pay_value)
                summary.last_fetched_at = last.fetched_at
                summary.chaos_equivalent = last.chaos_equivalent
                summary.bid_chaos = bid
                summary.ask_chaos = last.receive_value
                summary.spread_pct = _spread_pct(bid, last.receive_value)
                summary.low_confidence = last.low_confidence
            out.append(summary)

    return out


@router.get("/snapshots/{trade_id}", response_model=SnapshotSeries)
def snapshot_series_endpoint(
    trade_id: str,
    hours: int = Query(default=24, ge=1, le=24 * 30, description="Finestra temporale"),
    league: str = Query(default=None),
) -> SnapshotSeries:
    """Time-series di una currency nelle ultime `hours` ore.

    Ordinata ASC per fetched_at — il frontend grafica direttamente.
    """
    lg = league or settings.league
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)

    with get_session() as s:
        currency = s.execute(
            select(Currency).where(Currency.trade_id == trade_id)
        ).scalar_one_or_none()
        if currency is None:
            raise HTTPException(status_code=404, detail=f"currency not found: {trade_id}")

        snaps = s.execute(
            select(ExchangeSnapshot)
            .where(
                ExchangeSnapshot.currency_id == currency.id,
                ExchangeSnapshot.league == lg,
                ExchangeSnapshot.fetched_at >= cutoff,
            )
            .order_by(ExchangeSnapshot.fetched_at.asc())
        ).scalars().all()

        points = [
            SnapshotPoint(
                fetched_at=snap.fetched_at,
                chaos_equivalent=snap.chaos_equivalent,
                bid_chaos=_bid_from(snap.pay_value),
                ask_chaos=snap.receive_value,
                pay_listing_count=snap.pay_listing_count,
                receive_listing_count=snap.receive_listing_count,
                low_confidence=snap.low_confidence,
            )
            for snap in snaps
        ]

        return SnapshotSeries(
            trade_id=currency.trade_id,
            display_name=currency.display_name,
            league=lg,
            hours=hours,
            points=points,
        )


@router.post("/fetch/trigger", response_model=FetchTriggerResult)
async def trigger_fetch_endpoint(
    league: str = Query(default=None),
) -> FetchTriggerResult:
    """Forza un fetch immediato dalla UI ('refresh now').

    Ritorna quante righe sono state scritte (post-dedup).
    """
    lg = league or settings.league
    written = await run_fetch_now(league=lg)
    return FetchTriggerResult(written=written, league=lg)


@router.get("/arbitrage", response_model=ArbitrageResult)
def arbitrage_endpoint(
    league: str = Query(default=None),
    mode: str = Query(
        default="both",
        pattern="^(cycles|pairs|both)$",
        description="cycles=Bellman-Ford, pairs=mid-vs-spread, both=entrambi",
    ),
    min_profit_pct: float = Query(
        default=1.0, ge=0.0, le=100.0, description="Soglia profit% (cycles & pairs)."
    ),
    min_listing_count: int = Query(
        default=5, ge=0, description="Soglia di liquidità su entrambi i lati."
    ),
    max_spread_pct: float | None = Query(
        default=None, ge=0.0, le=500.0,
        description="Esclude currency con spread interno sopra soglia (%). "
                    "None = filtro off. Valore tipico: 30.",
    ),
    max_cycles: int = Query(default=20, ge=1, le=100),
    limit_pairs: int = Query(
        default=50, ge=1, le=500, description="Cap sul numero di coppie ritornate."
    ),
) -> ArbitrageResult:
    """Calcola opportunità di arbitrage sull'ultimo snapshot della lega.

    - `mode=cycles` → solo Bellman-Ford (cicli multi-hop via chaos-bridge).
    - `mode=pairs`  → solo mid-vs-spread (coppie Faustus-rate vs market-rate).
    - `mode=both`   → entrambi (default).

    Nota: il calcolo è in-process e leggero (~200 currency). Non cachato —
    la richiesta è tipicamente triggerata manualmente da UI ed è ok
    ricalcolare ogni volta.
    """
    lg = league or settings.league
    prices = get_latest_prices(league=lg)

    cycles_out: list[ArbitrageCycleOut] = []
    pairs_out: list[ArbitragePairOut] = []

    if mode in ("cycles", "both"):
        cycles = find_cycles(
            prices,
            min_profit_pct=min_profit_pct,
            min_listing_count=min_listing_count,
            max_cycles=max_cycles,
            max_spread_pct=max_spread_pct,
        )
        cycles_out = [
            ArbitrageCycleOut(
                path=list(c.path),
                profit_pct=c.profit_pct,
                min_listing_count=c.min_listing_count,
                low_confidence=c.low_confidence,
                step_rates=list(c.step_rates),
            )
            for c in cycles
        ]

    if mode in ("pairs", "both"):
        pairs = find_pair_opportunities(
            prices,
            min_profit_pct=min_profit_pct,
            min_listing_count=min_listing_count,
            max_spread_pct=max_spread_pct,
        )
        pairs_out = [
            ArbitragePairOut(
                source_trade_id=p.source_trade_id,
                target_trade_id=p.target_trade_id,
                faustus_rate=p.faustus_rate,
                market_rate=p.market_rate,
                profit_pct=p.profit_pct,
                min_listing_count=p.min_listing_count,
                low_confidence=p.low_confidence,
                source_spread_pct=p.source_spread_pct,
                target_spread_pct=p.target_spread_pct,
            )
            for p in pairs[:limit_pairs]
        ]

    return ArbitrageResult(
        league=lg,
        mode=mode,
        min_profit_pct=min_profit_pct,
        min_listing_count=min_listing_count,
        max_spread_pct=max_spread_pct,
        cycles=cycles_out,
        pairs=pairs_out,
    )


# ---------------------------------------------------------------------------
# FOB - Frusta Oracle Builder endpoints
# ---------------------------------------------------------------------------
from backend.services.fob_oracle import oracle as fob_oracle

class FobRequest(BaseModel):
    """Request model for FOB Oracle."""
    request: str
    pob_code: str | None = None
    league: str = settings.league

class FobRecommendation(BaseModel):
    name: str
    source: str
    url: str
    match_score: float
    dps: float
    ehp: float
    estimated_cost: dict
    progression: list

class FobResponse(BaseModel):
    intent: dict
    current_build: dict | None
    recommendations: list[FobRecommendation]

@router.post("/fob/oracle", response_model=FobResponse, tags=["fob"])
async def fob_oracle_endpoint(
    body: FobRequest,
) -> FobResponse:
    """FOB Frusta Oracle Builder - interpreta la richiesta in linguaggio naturale
    e restituisce build candidate con progressione 1->100 e costi reali."""
    result = fob_oracle(user_request=body.request, pob_code=body.pob_code)
    return FobResponse(**result)
