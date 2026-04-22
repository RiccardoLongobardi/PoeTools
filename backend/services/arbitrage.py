"""Arbitrage engine — Fase 2.

Due strategie di detection, complementari:

1. **Bellman-Ford sul grafo chaos-bridge** (`find_cycles`).
   Modellizza ogni trade A→B come "vendi A per chaos al bid_A, compra B con
   chaos al ask_B" → rate = bid_A / ask_B. Trasforma ogni rate in peso
   `-log(rate)`. Un ciclo a peso negativo = prodotto rate > 1 = arbitrage.

   In dati puliti e mercato efficiente, questo modello NON dovrebbe
   produrre cicli (somma spread ≥ 0). Quando invece li trova, è tipicamente
   un segnale di: dati stale (poe.ninja lag 10-30min), mercati incrociati
   (bid > ask su currency illiquide), o genuine opportunità di breve durata.

2. **Mid-vs-spread per coppia** (`find_pair_opportunities`).
   L'insight pratico su Faustus: Faustus scambia A↔B DIRETTAMENTE, bypassando
   il chaos-bridge. La sua rate è circa `chaos_eq_A / chaos_eq_B` (un solo
   spread, non due). Il detector confronta:

     - rate via Faustus implicito:  chaos_eq_A / chaos_eq_B
     - rate via market bridge:      bid_A / ask_B   (via chaos)

   Se il primo batte il secondo di almeno X%, c'è potenziale profit: Faustus
   ti paga A→B meglio di quanto potresti fare a mano via chaos. Questo è
   il segnale utile nel mondo reale.

**Scope:** l'engine è puro (no I/O, no DB). Il chiamante fornisce `CurrencyPrice`
già estratti, e l'engine ritorna opportunità pronte per UI/API.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input / output models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CurrencyPrice:
    """Snapshot corrente di una currency, input per l'engine.

    `bid_chaos` e `ask_chaos` sono già in chaos (derivati dai raw
    pay_value/receive_value di poe.ninja). None indica un lato di mercato
    assente — in quel caso la currency non può partecipare agli scambi di
    quel lato e viene esclusa dal grafo.
    """

    trade_id: str
    chaos_equivalent: float
    bid_chaos: float | None
    ask_chaos: float | None
    pay_listing_count: int
    receive_listing_count: int
    low_confidence: bool = False


@dataclass(frozen=True)
class ArbitrageCycle:
    """Un ciclo di arbitrage rilevato da Bellman-Ford.

    `path` è la sequenza ciclica di trade_id: il primo e l'ultimo coincidono.
    Es. ("divine-orb", "exalted-orb", "chaos-orb", "divine-orb") per un
    triangolo. `step_rates[i]` è il rate applicato per passare da path[i] a
    path[i+1].
    """

    path: tuple[str, ...]
    profit_pct: float
    min_listing_count: int
    low_confidence: bool
    step_rates: tuple[float, ...]

    @property
    def length(self) -> int:
        """Numero di hop (len(path) - 1, perché il ciclo chiude su sé stesso)."""
        return len(self.path) - 1


@dataclass(frozen=True)
class ArbitragePair:
    """Opportunità di tipo "mid vs spread" su una singola coppia.

    Rappresenta: "se Faustus ti scambia A→B al suo rate mid-to-mid
    (mid_A/mid_B, con mid = (bid+ask)/2), il rate via market-bridge è
    bid_A/ask_B. Se il primo batte il secondo di almeno `profit_pct`%,
    hai un vantaggio teorico."

    **Nota importante sulla semantica:** `faustus_rate` usa la mid
    empirica `(bid+ask)/2` — NON `chaos_equivalent`. Questo perché
    `chaos_equivalent` per currency con spread enorme (tipo orb-of-regret
    in late-league) lagga pesantemente verso un lato del mercato e produce
    falsi positivi a 3 cifre %. La mid empirica invece sta SEMPRE tra bid
    e ask per costruzione, e la differenza mid-vs-bridged-rate riflette il
    "valore del singolo spread" che Faustus risparmia.
    """

    source_trade_id: str
    target_trade_id: str
    faustus_rate: float  # mid_A / mid_B, con mid = (bid+ask)/2
    market_rate: float  # bid_A / ask_B
    profit_pct: float  # (faustus_rate / market_rate - 1) * 100
    min_listing_count: int
    low_confidence: bool
    # Spread interno delle currency coinvolte — utile per filtrare pair
    # dove almeno un lato è troppo wide per essere affidabile.
    source_spread_pct: float
    target_spread_pct: float


# ---------------------------------------------------------------------------
# Bellman-Ford cycle detection
# ---------------------------------------------------------------------------


@dataclass
class _Edge:
    """Arco del grafo. Tenuto separato da ArbitrageCycle perché mutable."""

    source: str
    target: str
    # weight = -log(rate). Minimizzare la somma = massimizzare il prodotto.
    weight: float
    rate: float  # salvato a parte per ricostruire step_rates senza exp()
    min_listing_count: int
    low_confidence: bool


def _spread_pct(p: CurrencyPrice) -> float | None:
    """Spread interno di una currency in %: |ask-bid| / mid * 100.

    None se manca un lato di mercato o mid è zero.
    """
    b, a = p.bid_chaos, p.ask_chaos
    if b is None or a is None:
        return None
    mid = (b + a) / 2.0
    if mid == 0:
        return None
    return abs(a - b) / mid * 100.0


def _build_graph(
    prices: Iterable[CurrencyPrice],
    *,
    min_listing_count: int,
    max_spread_pct: float | None = None,
) -> list[_Edge]:
    """Costruisce il grafo orientato chaos-bridge.

    Per ogni coppia ordinata (A, B) dove A != B, un arco A→B con:
        rate   = bid_A / ask_B     (chaos ricevuti vendendo 1 A, usati per comprare B)
        weight = -log(rate)

    Filtra via:
        - A senza bid (non vendibile sul lato pay), B senza ask (non comprabile)
        - liquidità (listing count) sotto soglia su entrambi i lati
        - `max_spread_pct`: se settato, esclude currency con spread interno
          oltre soglia (tipico sintomo di dati stale / illiquidità).
    """
    # Precomputo per evitare ripassate su attributi in loop interno.
    eligible: list[CurrencyPrice] = [
        p
        for p in prices
        if p.bid_chaos is not None
        and p.ask_chaos is not None
        and p.bid_chaos > 0
        and p.ask_chaos > 0
    ]
    if max_spread_pct is not None:
        eligible = [
            p for p in eligible
            if (sp := _spread_pct(p)) is not None and sp <= max_spread_pct
        ]

    edges: list[_Edge] = []
    for a in eligible:
        if a.pay_listing_count < min_listing_count:
            continue
        for b in eligible:
            if a.trade_id == b.trade_id:
                continue
            if b.receive_listing_count < min_listing_count:
                continue
            # a.bid_chaos e b.ask_chaos già verificati > 0 sopra.
            rate = a.bid_chaos / b.ask_chaos  # type: ignore[operator]
            edges.append(
                _Edge(
                    source=a.trade_id,
                    target=b.trade_id,
                    weight=-math.log(rate),
                    rate=rate,
                    min_listing_count=min(a.pay_listing_count, b.receive_listing_count),
                    low_confidence=a.low_confidence or b.low_confidence,
                )
            )
    return edges


def _detect_negative_cycle(
    nodes: list[str], edges: list[_Edge]
) -> Optional[tuple[str, dict[str, Optional[str]]]]:
    """Bellman-Ford con virtual source. Ritorna (start_node, predecessor_map)
    se un ciclo negativo esiste, altrimenti None.

    Tecnica: inizializziamo distance[v] = 0 per ogni v (equivale ad avere
    un source virtuale connesso a tutti i nodi con peso 0). Dopo |V|-1
    rilassamenti, se c'è ancora un arco rilassabile, il target di
    quell'arco è raggiungibile da un ciclo negativo.
    """
    dist: dict[str, float] = {n: 0.0 for n in nodes}
    pred: dict[str, Optional[str]] = {n: None for n in nodes}

    for _ in range(len(nodes) - 1):
        updated = False
        for e in edges:
            new_d = dist[e.source] + e.weight
            if new_d < dist[e.target]:
                dist[e.target] = new_d
                pred[e.target] = e.source
                updated = True
        if not updated:
            return None  # nessun ciclo negativo

    # Una pass in più: se rilassiamo ancora, siamo dentro/dopo un ciclo negativo.
    for e in edges:
        if dist[e.source] + e.weight < dist[e.target]:
            return e.target, pred
    return None


def _extract_cycle(start: str, pred: dict[str, Optional[str]]) -> list[str]:
    """Dalla predecessor map, estrae il ciclo che contiene `start`.

    Tecnica: fai |V| step all'indietro (garantisce che sei dentro al ciclo),
    poi continua fino a tornare al punto. La lista risultante è ciclica
    (primo == ultimo).
    """
    # Sleep into the cycle: dopo |V| backtrack siamo SICURAMENTE dentro al ciclo.
    v = start
    for _ in range(len(pred)):
        prev = pred[v]
        if prev is None:
            break  # degenere, ma non dovrebbe capitare qui
        v = prev

    # Ora cammina all'indietro finché non ritorni su v.
    cycle = [v]
    u = pred[v]
    while u is not None and u != v:
        cycle.append(u)
        u = pred[u]
    cycle.append(v)
    cycle.reverse()
    return cycle


def find_cycles(
    prices: Iterable[CurrencyPrice],
    *,
    min_profit_pct: float = 1.0,
    min_listing_count: int = 5,
    max_cycles: int = 20,
    max_spread_pct: float | None = None,
) -> list[ArbitrageCycle]:
    """Trova cicli di arbitrage via Bellman-Ford sul grafo chaos-bridge.

    Args:
        prices: snapshot corrente del mercato.
        min_profit_pct: scarta cicli con profit < X%. Default 1% per tagliare rumore.
        min_listing_count: esclude currency/coppie con liquidità sotto soglia.
        max_cycles: limite di sicurezza sul numero di cicli rilevati. Dopo
            aver trovato uno, rimuoviamo un arco del ciclo e ri-cerchiamo —
            così evitiamo di restituire lo stesso ciclo identico N volte.
        max_spread_pct: se settato, esclude currency con spread interno
            (|ask-bid|/mid) sopra soglia. Utile per evitare rumore da
            illiquidità. `None` = filtro disattivato.

    Returns:
        Lista di `ArbitrageCycle` ordinati per profit decrescente.
    """
    prices_list = list(prices)
    edges = _build_graph(
        prices_list,
        min_listing_count=min_listing_count,
        max_spread_pct=max_spread_pct,
    )
    if not edges:
        return []

    nodes = sorted({p.trade_id for p in prices_list})
    edges_by_key: dict[tuple[str, str], _Edge] = {
        (e.source, e.target): e for e in edges
    }

    found: list[ArbitrageCycle] = []
    remaining_edges = edges.copy()

    for _ in range(max_cycles):
        result = _detect_negative_cycle(nodes, remaining_edges)
        if result is None:
            break
        start, pred = result
        path = _extract_cycle(start, pred)
        if len(path) < 3:  # almeno 2 hop: A → B → A
            break

        # Ricostruisce rate e stats lungo il path.
        step_rates: list[float] = []
        min_liq = float("inf")
        low_conf = False
        valid = True
        for i in range(len(path) - 1):
            edge = edges_by_key.get((path[i], path[i + 1]))
            if edge is None:
                # Non dovrebbe capitare — edges_by_key contiene tutti gli edges
                # del grafo. Se capita, saltiamo il ciclo.
                valid = False
                break
            step_rates.append(edge.rate)
            min_liq = min(min_liq, edge.min_listing_count)
            low_conf = low_conf or edge.low_confidence

        if not valid:
            break

        product = 1.0
        for r in step_rates:
            product *= r
        profit_pct = (product - 1.0) * 100.0

        if profit_pct >= min_profit_pct:
            found.append(
                ArbitrageCycle(
                    path=tuple(path),
                    profit_pct=profit_pct,
                    min_listing_count=int(min_liq),
                    low_confidence=low_conf,
                    step_rates=tuple(step_rates),
                )
            )

        # Rimuovi l'arco più debole (weight più alto = rate più basso) del ciclo
        # e ri-cerca, per trovare eventuali altri cicli distinti.
        weakest_idx = max(
            range(len(path) - 1),
            key=lambda i: edges_by_key[(path[i], path[i + 1])].weight,
        )
        weakest_key = (path[weakest_idx], path[weakest_idx + 1])
        remaining_edges = [
            e for e in remaining_edges if (e.source, e.target) != weakest_key
        ]

    found.sort(key=lambda c: c.profit_pct, reverse=True)
    return found


# ---------------------------------------------------------------------------
# Mid-vs-spread detector
# ---------------------------------------------------------------------------


def find_pair_opportunities(
    prices: Iterable[CurrencyPrice],
    *,
    min_profit_pct: float = 1.0,
    min_listing_count: int = 5,
    max_spread_pct: float | None = None,
) -> list[ArbitragePair]:
    """Per ogni coppia (A, B), confronta il Faustus rate mid-to-mid col market bridge.

    **Semantica:** ipotizziamo che Faustus scambi A→B al rate
    `mid_A / mid_B` dove `mid = (bid + ask) / 2` — un solo "mezzo spread"
    dal lato Faustus. Il rate equivalente se dovessi farlo a mano via chaos
    sul market è `bid_A / ask_B` — due spread incrociati.

    **Perché mid empirica e non `chaos_equivalent`?** `chaos_equivalent` è
    una media ponderata che su currency con spread enorme (illiquide,
    endgame league) si può parcheggiare su un lato del mercato, generando
    profitti fantasma a 3 cifre %. `mid = (bid+ask)/2` sta SEMPRE fra i
    due lati per costruzione, quindi il segnale è robusto.

    Il profit che emerge (~mezzo spread) riflette il vantaggio teorico di
    Faustus rispetto a un round-trip sul market — da validare in-game
    perché il rate vero di Faustus non ci è noto.

    Args:
        prices: snapshot del mercato.
        min_profit_pct: soglia di profit per riportare la coppia.
        min_listing_count: soglia di liquidità su entrambi i lati.
        max_spread_pct: se settato, esclude currency con spread interno
            (|ask-bid|/mid) sopra soglia. `None` = filtro off.

    Returns:
        Lista di `ArbitragePair` ordinati per profit decrescente.
    """
    # Precomputo mid e spread_pct per ogni currency eligible.
    eligible: list[tuple[CurrencyPrice, float, float]] = []
    for p in prices:
        if p.bid_chaos is None or p.ask_chaos is None:
            continue
        if p.bid_chaos <= 0 or p.ask_chaos <= 0:
            continue
        mid = (p.bid_chaos + p.ask_chaos) / 2.0
        if mid <= 0:
            continue
        spread = abs(p.ask_chaos - p.bid_chaos) / mid * 100.0
        if max_spread_pct is not None and spread > max_spread_pct:
            continue
        eligible.append((p, mid, spread))

    out: list[ArbitragePair] = []
    for a, mid_a, spread_a in eligible:
        if a.pay_listing_count < min_listing_count:
            continue
        for b, mid_b, spread_b in eligible:
            if a.trade_id == b.trade_id:
                continue
            if b.receive_listing_count < min_listing_count:
                continue

            faustus_rate = mid_a / mid_b
            market_rate = a.bid_chaos / b.ask_chaos  # type: ignore[operator]
            if market_rate <= 0:
                continue

            profit_pct = (faustus_rate / market_rate - 1.0) * 100.0
            if profit_pct < min_profit_pct:
                continue

            out.append(
                ArbitragePair(
                    source_trade_id=a.trade_id,
                    target_trade_id=b.trade_id,
                    faustus_rate=faustus_rate,
                    market_rate=market_rate,
                    profit_pct=profit_pct,
                    min_listing_count=min(
                        a.pay_listing_count, b.receive_listing_count
                    ),
                    low_confidence=a.low_confidence or b.low_confidence,
                    source_spread_pct=spread_a,
                    target_spread_pct=spread_b,
                )
            )

    out.sort(key=lambda p: p.profit_pct, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Summary dataclass (utile per l'API: entrambi i detector in un colpo solo)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArbitrageReport:
    """Output congiunto dei due detector — utile per API/CLI."""

    cycles: list[ArbitrageCycle] = field(default_factory=list)
    pairs: list[ArbitragePair] = field(default_factory=list)


def run_all(
    prices: Iterable[CurrencyPrice],
    *,
    min_profit_pct: float = 1.0,
    min_listing_count: int = 5,
    max_spread_pct: float | None = None,
) -> ArbitrageReport:
    """Esegue entrambi i detector su un singolo snapshot."""
    prices_list = list(prices)
    cycles = find_cycles(
        prices_list,
        min_profit_pct=min_profit_pct,
        min_listing_count=min_listing_count,
        max_spread_pct=max_spread_pct,
    )
    pairs = find_pair_opportunities(
        prices_list,
        min_profit_pct=min_profit_pct,
        min_listing_count=min_listing_count,
        max_spread_pct=max_spread_pct,
    )
    return ArbitrageReport(cycles=cycles, pairs=pairs)


# ---------------------------------------------------------------------------
# DB adapter — unica funzione con side-effects I/O in questo modulo.
# Tenuta qui per comodità (fa da "feed" all'engine puro sopra), ma l'engine
# stesso rimane testabile senza DB: passagli direttamente `CurrencyPrice`.
# ---------------------------------------------------------------------------


def get_latest_prices(league: str) -> list[CurrencyPrice]:
    """Estrae l'ultimo snapshot per ogni currency della lega come CurrencyPrice.

    Converte `ExchangeSnapshot` → `CurrencyPrice` applicando la stessa
    semantica chaos-denominata usata dalle API (bid = 1/pay_value, ask =
    receive_value).

    Snapshot senza `pay_value` o `receive_value` mantengono `None` sul
    lato mancante — l'engine li filtrerà dal grafo automaticamente.

    Nota: import-lazy di db/models per evitare di richiedere il DB quando
    l'engine è usato solo con fixtures in test.
    """
    from sqlalchemy import select

    from backend.db import get_session
    from backend.models import Currency, ExchangeSnapshot

    with get_session() as s:
        # Una sola query: ordina ASC per fetched_at, poi "dedup by overwrite"
        # in Python. Per ~200 currency è trascurabile. L'indice
        # ix_snapshot_league_time fa sì che il piano sia un range scan.
        stmt = (
            select(ExchangeSnapshot, Currency.trade_id)
            .join(Currency, Currency.id == ExchangeSnapshot.currency_id)
            .where(ExchangeSnapshot.league == league)
            .order_by(ExchangeSnapshot.fetched_at.asc())
        )

        last_by_id: dict[str, tuple[ExchangeSnapshot, str]] = {}
        for snap, trade_id in s.execute(stmt).all():
            last_by_id[trade_id] = (snap, trade_id)

    out: list[CurrencyPrice] = []
    for snap, trade_id in last_by_id.values():
        bid = 1.0 / snap.pay_value if snap.pay_value else None
        ask = snap.receive_value
        out.append(
            CurrencyPrice(
                trade_id=trade_id,
                chaos_equivalent=snap.chaos_equivalent,
                bid_chaos=bid,
                ask_chaos=ask,
                pay_listing_count=snap.pay_listing_count or 0,
                receive_listing_count=snap.receive_listing_count or 0,
                low_confidence=snap.low_confidence,
            )
        )
    return out
