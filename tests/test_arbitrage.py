"""Test dell'arbitrage engine.

L'engine è puro (no DB, no I/O) quindi testarlo è facile: gli passiamo
`CurrencyPrice` craftati con scenari noti e verifichiamo l'output.

Casi coperti:

- **Clean market** (bid < ask ovunque) → nessun ciclo trovato.
- **Triangolo crossed** (rate_A→B * rate_B→C * rate_C→A > 1) → ciclo trovato,
  profit% corrisponde al prodotto - 1.
- **Mid-vs-spread**: craft una coppia dove il Faustus rate implicito
  (chaos_eq_A / chaos_eq_B) batte il market rate (bid_A / ask_B).
- **Filtri**: liquidità sotto soglia esclude; profit sotto soglia non riporta.
- **Edge cases**: bid/ask None, lista vuota, singola currency.
- **Low-confidence propagation**: una currency low_conf nel path/coppia →
  opportunity.low_confidence = True.
"""

from __future__ import annotations

from backend.services.arbitrage import (
    ArbitragePair,
    CurrencyPrice,
    find_cycles,
    find_pair_opportunities,
    run_all,
)


# ---------------------------------------------------------------------------
# Helpers per costruire CurrencyPrice con default ragionevoli
# ---------------------------------------------------------------------------


def _price(
    trade_id: str,
    *,
    chaos_eq: float,
    bid: float | None,
    ask: float | None,
    pay_listings: int = 100,
    recv_listings: int = 100,
    low_conf: bool = False,
) -> CurrencyPrice:
    """Shortcut — crea CurrencyPrice con liquidità abbondante di default."""
    return CurrencyPrice(
        trade_id=trade_id,
        chaos_equivalent=chaos_eq,
        bid_chaos=bid,
        ask_chaos=ask,
        pay_listing_count=pay_listings,
        receive_listing_count=recv_listings,
        low_confidence=low_conf,
    )


# ---------------------------------------------------------------------------
# find_cycles
# ---------------------------------------------------------------------------


def test_empty_prices_returns_no_cycles() -> None:
    assert find_cycles([]) == []


def test_single_currency_returns_no_cycles() -> None:
    p = _price("chaos", chaos_eq=1.0, bid=1.0, ask=1.0)
    assert find_cycles([p]) == []


def test_clean_market_finds_no_cycle() -> None:
    """Mercato pulito: bid < ask ovunque → nessun arbitrage possibile.

    Questo è il caso "normale": su dati efficienti il detector è silenzioso.
    """
    prices = [
        _price("a", chaos_eq=10.0, bid=9.5, ask=10.5),
        _price("b", chaos_eq=5.0, bid=4.9, ask=5.1),
        _price("c", chaos_eq=1.0, bid=0.99, ask=1.01),
    ]
    assert find_cycles(prices, min_profit_pct=0.01) == []


def test_crossed_triangle_finds_cycle() -> None:
    """Triangolo A→B→C→A con prodotto rate > 1 → ciclo trovato.

    Costruito con bid > ask (mercato invertito, "crossed"): vende A al bid
    alto, compra B al ask basso, etc.

    Craftato su tre currency:
      A: bid=12, ask=10  (bid>ask, crossed)
      B: bid=6, ask=5    (bid>ask, crossed)
      C: bid=1.2, ask=1  (bid>ask, crossed)

    Rate A→B = 12/5 = 2.4     → 1 unit A dà 2.4 units B
    Rate B→C = 6/1 = 6        → 2.4 B dà 14.4 C
    Rate C→A = 1.2/10 = 0.12  → 14.4 C dà 1.728 A
    Prodotto = 2.4*6*0.12 = 1.728 → +72.8%
    """
    prices = [
        _price("a", chaos_eq=11.0, bid=12.0, ask=10.0),
        _price("b", chaos_eq=5.5, bid=6.0, ask=5.0),
        _price("c", chaos_eq=1.1, bid=1.2, ask=1.0),
    ]
    cycles = find_cycles(prices, min_profit_pct=1.0)
    assert len(cycles) >= 1

    top = cycles[0]
    # Il path è ciclico: primo == ultimo
    assert top.path[0] == top.path[-1]
    # Tutti i nodi del ciclo provengono dal nostro set di input
    assert set(top.path[:-1]).issubset({"a", "b", "c"})
    # Almeno 2 hop (len path >= 3 perché ciclo include la chiusura)
    assert len(top.path) >= 3
    # Profit positivo e significativo (2-hop minimo: +44%, 3-hop: +72.8%)
    assert top.profit_pct > 1.0
    # step_rates ha length = hops
    assert len(top.step_rates) == top.length


def test_cycle_respects_min_profit_threshold() -> None:
    """Cicli sotto soglia non vengono riportati."""
    prices = [
        _price("a", chaos_eq=10.0, bid=10.05, ask=10.0),
        _price("b", chaos_eq=5.0, bid=5.02, ask=5.0),
    ]
    # Profit atteso ~(10.05/10 * 5.02/5) - 1 ≈ (1.005*1.004) - 1 ≈ +0.902%
    assert find_cycles(prices, min_profit_pct=5.0) == []


def test_cycle_respects_min_listing_count() -> None:
    """Currency con pay_listings sotto soglia esclusa come sorgente.

    Scenario: solo 'a' è crossed (bid>ask); b e c hanno mercato pulito,
    quindi da soli non formano cicli. Filtrando 'a' per bassa liquidità,
    nessun ciclo deve rimanere.
    """
    prices = [
        # Crossed (arbitrage possibile), ma pay_listings=3 sotto soglia
        _price("a", chaos_eq=11.0, bid=12.0, ask=10.0, pay_listings=3),
        # Mercato pulito: bid < ask
        _price("b", chaos_eq=5.0, bid=4.95, ask=5.05),
        _price("c", chaos_eq=1.0, bid=0.98, ask=1.02),
    ]
    # Escludendo 'a' come source, rimane solo un mercato pulito → no cycles
    cycles = find_cycles(prices, min_profit_pct=1.0, min_listing_count=5)
    assert cycles == []
    # Sanity: senza il filtro, 'a' è source e dovrebbero esserci cicli
    cycles_unfiltered = find_cycles(prices, min_profit_pct=1.0, min_listing_count=0)
    assert len(cycles_unfiltered) >= 1


def test_cycle_propagates_low_confidence() -> None:
    """Se qualsiasi currency nel path è low_conf → cycle.low_confidence = True."""
    prices = [
        _price("a", chaos_eq=11.0, bid=12.0, ask=10.0, low_conf=True),
        _price("b", chaos_eq=5.5, bid=6.0, ask=5.0),
        _price("c", chaos_eq=1.1, bid=1.2, ask=1.0),
    ]
    cycles = find_cycles(prices, min_profit_pct=1.0)
    assert len(cycles) >= 1
    assert cycles[0].low_confidence is True


def test_price_missing_bid_or_ask_excluded() -> None:
    """Currency con bid=None o ask=None non partecipa al grafo."""
    prices = [
        _price("a", chaos_eq=11.0, bid=None, ask=10.0),
        _price("b", chaos_eq=5.5, bid=6.0, ask=5.0),
    ]
    assert find_cycles(prices, min_profit_pct=1.0) == []


# ---------------------------------------------------------------------------
# find_pair_opportunities
# ---------------------------------------------------------------------------


def test_pair_finds_faustus_beats_market() -> None:
    """Craft: Faustus rate molto migliore del market bridged rate.

    A: chaos_eq=100, bid=80,  ask=120   → market_rate A→B = 80/ask_B
    B: chaos_eq=10,  bid=9.5, ask=10.5

    Faustus rate A→B = 100/10 = 10    (1 A ti dà 10 B via Faustus)
    Market rate A→B  = 80/10.5 ≈ 7.619 (1 A ti dà ~7.62 B via chaos-bridge)
    Profit_pct = (10 / 7.619 - 1) * 100 ≈ +31.25%
    """
    prices = [
        _price("a", chaos_eq=100.0, bid=80.0, ask=120.0),
        _price("b", chaos_eq=10.0, bid=9.5, ask=10.5),
    ]
    pairs = find_pair_opportunities(prices, min_profit_pct=1.0)
    # Attese: A→B profittevole, B→A no (simmetrico, spread-negativo)
    pair_ab = next((p for p in pairs if p.source_trade_id == "a" and p.target_trade_id == "b"), None)
    assert pair_ab is not None
    assert 25.0 < pair_ab.profit_pct < 40.0


def test_pair_respects_min_profit() -> None:
    """Soglia di profit rispettata."""
    prices = [
        _price("a", chaos_eq=100.0, bid=95.0, ask=105.0),
        _price("b", chaos_eq=10.0, bid=9.95, ask=10.05),
    ]
    # Faustus A→B = 10; Market = 95/10.05 ≈ 9.45; profit ≈ +5.8%
    assert find_pair_opportunities(prices, min_profit_pct=10.0) == []
    pairs = find_pair_opportunities(prices, min_profit_pct=1.0)
    assert len(pairs) >= 1


def test_pair_respects_liquidity() -> None:
    """Coppie con liquidità sotto soglia sono escluse."""
    prices = [
        _price("a", chaos_eq=100.0, bid=80.0, ask=120.0, pay_listings=2),
        _price("b", chaos_eq=10.0, bid=9.5, ask=10.5),
    ]
    pairs = find_pair_opportunities(prices, min_profit_pct=1.0, min_listing_count=5)
    # A→B escluso perché pay_listings di A è 2 < 5
    ab = [p for p in pairs if p.source_trade_id == "a" and p.target_trade_id == "b"]
    assert ab == []


def test_pair_skips_missing_sides() -> None:
    """Currency con bid o ask mancanti non partecipa."""
    prices = [
        _price("a", chaos_eq=100.0, bid=None, ask=120.0),
        _price("b", chaos_eq=10.0, bid=9.5, ask=10.5),
    ]
    # A non ha bid → nessuna coppia A→* possibile
    pairs = find_pair_opportunities(prices, min_profit_pct=0.0)
    assert all(p.source_trade_id != "a" for p in pairs)


def test_pair_sorted_by_profit_desc() -> None:
    """Output ordinato per profit% decrescente."""
    prices = [
        _price("a", chaos_eq=100.0, bid=80.0, ask=120.0),
        _price("b", chaos_eq=10.0, bid=9.5, ask=10.5),
        _price("c", chaos_eq=1.0, bid=0.5, ask=1.5),
    ]
    pairs = find_pair_opportunities(prices, min_profit_pct=0.0)
    profits = [p.profit_pct for p in pairs]
    assert profits == sorted(profits, reverse=True)


def test_pair_propagates_low_confidence() -> None:
    prices = [
        _price("a", chaos_eq=100.0, bid=80.0, ask=120.0, low_conf=True),
        _price("b", chaos_eq=10.0, bid=9.5, ask=10.5),
    ]
    pairs = find_pair_opportunities(prices, min_profit_pct=1.0)
    assert all(isinstance(p, ArbitragePair) for p in pairs)
    # Almeno una coppia coinvolge 'a' (low_conf)
    assert any(p.low_confidence for p in pairs)


def test_pair_uses_mid_rate_not_chaos_equivalent() -> None:
    """Regressione: il faustus_rate deve essere mid-based, non chaos_eq-based.

    Costruisco una currency dove chaos_eq è diverso dalla mid empirica.
    Questo simula una illiquidity drift come orb-of-regret (chaos_eq lagga
    su un lato del mercato). Il nuovo detector NON deve usare chaos_eq.
    """
    # Currency 'illiquid' con chaos_eq=1.5 ma vera mid ≈ 0.875
    # (bid=0.25, ask=1.5, mid=(0.25+1.5)/2=0.875)
    prices = [
        _price("illiquid", chaos_eq=1.5, bid=0.25, ask=1.5),
        _price("divine", chaos_eq=312.0, bid=304.0, ask=330.0),
    ]
    pairs = find_pair_opportunities(prices, min_profit_pct=0.0)
    pair = next(
        (p for p in pairs if p.source_trade_id == "illiquid" and p.target_trade_id == "divine"),
        None,
    )
    assert pair is not None
    # Expected faustus_rate = mid_illiquid / mid_divine = 0.875 / 317.0 ≈ 0.00276
    mid_illiquid = (0.25 + 1.5) / 2
    mid_divine = (304.0 + 330.0) / 2
    expected = mid_illiquid / mid_divine
    assert abs(pair.faustus_rate - expected) < 1e-9, (
        f"faustus_rate={pair.faustus_rate} != mid-based expected={expected}"
    )
    # Expected spread_pct illiquid = |1.5-0.25|/0.875 * 100 ≈ 142.86
    assert 140 < pair.source_spread_pct < 145


def test_pair_max_spread_filter_excludes_wide_currencies() -> None:
    """Il filtro max_spread_pct esclude currency con spread interno sopra soglia.

    Regressione sul caso orb-of-regret: con max_spread=30% il filtro taglia
    ogni coppia che coinvolge una currency con spread >30%.
    """
    prices = [
        # Spread interno ~143% — deve essere scartato
        _price("regret", chaos_eq=1.5, bid=0.25, ask=1.5),
        # Spread ~8% — OK
        _price("divine", chaos_eq=317.0, bid=304.0, ask=330.0),
        # Spread ~10% — OK
        _price("exalt", chaos_eq=60.0, bid=57.0, ask=63.0),
    ]
    # Senza filtro: regret compare (generando falsi profit enormi)
    unfiltered = find_pair_opportunities(prices, min_profit_pct=0.0)
    assert any(p.source_trade_id == "regret" or p.target_trade_id == "regret"
               for p in unfiltered)

    # Con filtro al 30%: regret escluso completamente
    filtered = find_pair_opportunities(
        prices, min_profit_pct=0.0, max_spread_pct=30.0
    )
    assert all(
        p.source_trade_id != "regret" and p.target_trade_id != "regret"
        for p in filtered
    )
    # Ma divine↔exalt passa
    assert any(
        {p.source_trade_id, p.target_trade_id} == {"divine", "exalt"}
        for p in filtered
    )


def test_cycle_max_spread_filter() -> None:
    """max_spread_pct filtra anche il cycles detector."""
    prices = [
        # Tre crossed con spread "medio" ~18% — passano max_spread=30
        _price("a", chaos_eq=11.0, bid=12.0, ask=10.0),
        _price("b", chaos_eq=5.5, bid=6.0, ask=5.0),
        _price("c", chaos_eq=1.1, bid=1.2, ask=1.0),
    ]
    # Senza filtro: cicli trovati
    unfiltered = find_cycles(prices, min_profit_pct=1.0)
    assert len(unfiltered) >= 1
    # Filtro max_spread=10 esclude TUTTE (spread ~18% > 10)
    filtered = find_cycles(prices, min_profit_pct=1.0, max_spread_pct=10.0)
    assert filtered == []


# ---------------------------------------------------------------------------
# run_all — sanity: non esplode, combina i due detector
# ---------------------------------------------------------------------------


def test_run_all_combines_detectors() -> None:
    """Mix scenario: triangolo crossed (per cycles) + coppia healthy (per pairs).

    Con la nuova semantica mid-based, coppie crossed NON producono pair
    opportunities (mid sta sempre fra bid e ask). Le pair emergono invece
    su mercati healthy con spread: il detector flagga il "mezzo spread"
    che Faustus risparmierebbe rispetto al round-trip market.
    """
    prices = [
        # Triangolo crossed → cycles detector lo trova
        _price("a", chaos_eq=11.0, bid=12.0, ask=10.0),
        _price("b", chaos_eq=5.5, bid=6.0, ask=5.0),
        _price("c", chaos_eq=1.1, bid=1.2, ask=1.0),
        # Coppia healthy con spread ampio → pair detector la flagga
        _price("d", chaos_eq=100.0, bid=80.0, ask=120.0),
        _price("e", chaos_eq=10.0, bid=9.5, ask=10.5),
    ]
    report = run_all(prices, min_profit_pct=1.0, min_listing_count=5)
    assert len(report.cycles) >= 1
    assert len(report.pairs) >= 1


def test_run_all_on_clean_market_returns_empty() -> None:
    """Mercato efficiente: niente cicli, niente coppie sopra soglia."""
    prices = [
        _price("a", chaos_eq=10.0, bid=9.9, ask=10.1),
        _price("b", chaos_eq=5.0, bid=4.95, ask=5.05),
    ]
    report = run_all(prices, min_profit_pct=5.0, min_listing_count=5)
    assert report.cycles == []
    assert report.pairs == []


# ---------------------------------------------------------------------------
# get_latest_prices — DB adapter (unico test che tocca DB)
# ---------------------------------------------------------------------------


def test_get_latest_prices_returns_last_snapshot_per_currency(in_memory_db) -> None:
    """Verifica che get_latest_prices ritorni SOLO l'ultimo snapshot per currency.

    Inseriamo 2 snapshot sulla stessa currency a timestamp diversi e
    verifichiamo che solo il più recente venga riportato, con bid/ask
    derivati correttamente da pay_value/receive_value.
    """
    from datetime import datetime, timedelta, timezone

    from backend.db import get_session
    from backend.models import Currency, ExchangeSnapshot
    from backend.services.arbitrage import get_latest_prices

    now = datetime.now(tz=timezone.utc)

    with get_session() as s:
        a = Currency(trade_id="a", display_name="A", icon_url=None, category="Currency")
        b = Currency(trade_id="b", display_name="B", icon_url=None, category="Currency")
        s.add_all([a, b])
        s.flush()

        # Snapshot vecchio su A
        s.add(ExchangeSnapshot(
            currency_id=a.id, league="Mirage",
            fetched_at=now - timedelta(hours=1),
            chaos_equivalent=10.0, pay_value=0.1, receive_value=9.5,
            pay_listing_count=50, receive_listing_count=60,
            low_confidence=False,
        ))
        # Snapshot nuovo su A
        s.add(ExchangeSnapshot(
            currency_id=a.id, league="Mirage",
            fetched_at=now,
            chaos_equivalent=11.0, pay_value=0.08, receive_value=12.0,
            pay_listing_count=70, receive_listing_count=80,
            low_confidence=True,
        ))
        # Un unico snapshot su B
        s.add(ExchangeSnapshot(
            currency_id=b.id, league="Mirage",
            fetched_at=now,
            chaos_equivalent=5.0, pay_value=0.2, receive_value=4.9,
            pay_listing_count=30, receive_listing_count=40,
            low_confidence=False,
        ))
        # Snapshot su altra lega: deve essere ignorato
        s.add(ExchangeSnapshot(
            currency_id=a.id, league="Standard",
            fetched_at=now,
            chaos_equivalent=999.0, pay_value=0.01, receive_value=999.0,
            pay_listing_count=1, receive_listing_count=1,
            low_confidence=False,
        ))

    prices = get_latest_prices(league="Mirage")
    by_id = {p.trade_id: p for p in prices}

    # 2 currency, 2 risultati
    assert set(by_id.keys()) == {"a", "b"}

    # A deve essere il nuovo snapshot (chaos_eq=11.0), NON il vecchio (10.0)
    assert by_id["a"].chaos_equivalent == 11.0
    # bid = 1/pay_value = 1/0.08 = 12.5
    assert by_id["a"].bid_chaos == 12.5
    # ask = receive_value = 12.0
    assert by_id["a"].ask_chaos == 12.0
    assert by_id["a"].pay_listing_count == 70
    assert by_id["a"].receive_listing_count == 80
    assert by_id["a"].low_confidence is True

    # B sanity
    assert by_id["b"].chaos_equivalent == 5.0
    assert by_id["b"].bid_chaos == 5.0  # 1/0.2
    assert by_id["b"].ask_chaos == 4.9


def test_get_latest_prices_empty_db(in_memory_db) -> None:
    from backend.services.arbitrage import get_latest_prices

    assert get_latest_prices(league="Mirage") == []
