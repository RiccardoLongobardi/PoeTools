"""Test unit per PoeNinjaSource.

Usiamo httpx.MockTransport (via fixture `mock_httpx_client`) così i test
non toccano la rete, ma esercitano comunque tutto il code path reale di
PoeNinjaSource: costruzione query, parsing pydantic, conversione in
ExchangeQuote.
"""

from __future__ import annotations

import httpx
import pytest

from backend.datasource.base import CurrencyInfo, ExchangeQuote
from backend.datasource.poe_ninja import PoeNinjaSource, _slugify


# ---------------------------------------------------------------------------
# fetch_currency_overview
# ---------------------------------------------------------------------------


async def test_fetch_currency_returns_expected_count(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_currency_overview(league="Mirage")
    finally:
        await src.aclose()

    # La fixture ha 5 lines in Currency.
    assert len(quotes) == 5
    assert all(isinstance(q, ExchangeQuote) for q in quotes)


async def test_fetch_currency_maps_fields(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_currency_overview(league="Mirage")
    finally:
        await src.aclose()

    divine = next(q for q in quotes if q.currency_trade_id == "divine-orb")
    assert divine.chaos_equivalent == pytest.approx(222.75)
    assert divine.pay_value == pytest.approx(220.0)
    assert divine.receive_value == pytest.approx(225.5)
    assert divine.pay_listing_count == 180
    assert divine.receive_listing_count == 140
    assert divine.low_confidence is False
    assert divine.league == "Mirage"


async def test_fetch_currency_low_confidence_flag(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    """La fixture 'Regal Orb' ha lowConfidencePaySparkLine non-null: deve risultare low_conf."""
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_currency_overview(league="Mirage")
    finally:
        await src.aclose()

    regal = next(q for q in quotes if q.currency_trade_id == "regal-orb")
    assert regal.low_confidence is True


async def test_fetch_currency_handles_missing_pay_side(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    """Regal Orb non ha `pay` (null): pay_value deve essere None, non crash."""
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_currency_overview(league="Mirage")
    finally:
        await src.aclose()

    regal = next(q for q in quotes if q.currency_trade_id == "regal-orb")
    assert regal.pay_value is None
    assert regal.pay_listing_count is None
    assert regal.receive_value == pytest.approx(0.25)


async def test_fetch_currency_sets_fetched_at(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_currency_overview(league="Mirage")
    finally:
        await src.aclose()

    assert quotes[0].fetched_at is not None
    assert quotes[0].fetched_at.tzinfo is not None, "datetime deve essere timezone-aware"


# ---------------------------------------------------------------------------
# fetch_fragment_overview
# ---------------------------------------------------------------------------


async def test_fetch_fragment_works(mock_httpx_client: httpx.AsyncClient) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_fragment_overview(league="Mirage")
    finally:
        await src.aclose()

    assert len(quotes) == 2
    ids = {q.currency_trade_id for q in quotes}
    assert ids == {"sacrifice-at-dusk", "divine-vessel"}


# ---------------------------------------------------------------------------
# list_currencies
# ---------------------------------------------------------------------------


async def test_list_currencies_aggregates_currency_and_fragment(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        infos = await src.list_currencies(league="Mirage")
    finally:
        await src.aclose()

    # 5 currency + 2 fragment = 7 (nessun overlap nelle fixture)
    assert len(infos) == 7
    assert all(isinstance(c, CurrencyInfo) for c in infos)
    categories = {c.category for c in infos}
    assert categories == {"Currency", "Fragment"}


async def test_list_currencies_trade_ids_are_unique(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        infos = await src.list_currencies(league="Mirage")
    finally:
        await src.aclose()

    ids = [c.trade_id for c in infos]
    assert len(ids) == len(set(ids)), "deve dedupare per trade_id"


# ---------------------------------------------------------------------------
# fetch_all
# ---------------------------------------------------------------------------


async def test_fetch_all_combines_categories(
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    src = PoeNinjaSource(client=mock_httpx_client)
    try:
        quotes = await src.fetch_all(league="Mirage")
    finally:
        await src.aclose()

    # 5 + 2 = 7
    assert len(quotes) == 7


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert _slugify("Chaos Orb") == "chaos-orb"
    assert _slugify("Orb of Annulment") == "orb-of-annulment"
    assert _slugify("   Divine  Orb  ") == "divine-orb"


def test_slugify_handles_special_chars() -> None:
    assert _slugify("Sacrifice at Dusk!") == "sacrifice-at-dusk"
    assert _slugify("Al-Hezmin's Crest") == "al-hezmin-s-crest"
