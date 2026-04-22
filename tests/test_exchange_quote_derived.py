"""Test dei campi derivati di ExchangeQuote (bid/ask/mid/spread).

Questi test verificano solo la matematica delle @computed_field, non
toccano poe.ninja né il fetcher. Sono il "contratto" che il resto dell'app
può assumere: ovunque serva un prezzo in chaos, usa bid/ask/mid, non
pay_value/receive_value grezzi.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.datasource.base import ExchangeQuote


def _make_quote(
    *,
    pay_value: float | None = None,
    receive_value: float | None = None,
    chaos_equivalent: float = 1.0,
) -> ExchangeQuote:
    """Helper: crea un quote minimale per testare i campi derivati."""
    return ExchangeQuote(
        currency_trade_id="test",
        league="Mirage",
        fetched_at=datetime.now(tz=timezone.utc),
        chaos_equivalent=chaos_equivalent,
        pay_value=pay_value,
        receive_value=receive_value,
    )


# ---------------------------------------------------------------------------
# bid_chaos = 1 / pay_value
# ---------------------------------------------------------------------------


def test_bid_chaos_is_reciprocal_of_pay_value() -> None:
    # Semantica poe.ninja: pay.value è *currency per chaos*, quindi il prezzo
    # in chaos di 1 unità di currency è il suo reciproco.
    q = _make_quote(pay_value=0.00328)
    assert q.bid_chaos == pytest.approx(1 / 0.00328)


def test_bid_chaos_none_when_pay_missing() -> None:
    q = _make_quote(pay_value=None, receive_value=100.0)
    assert q.bid_chaos is None


def test_bid_chaos_none_when_pay_is_zero() -> None:
    # Difesa contro division-by-zero. Mercati vuoti possono avere pay=0.
    q = _make_quote(pay_value=0.0)
    assert q.bid_chaos is None


# ---------------------------------------------------------------------------
# ask_chaos = receive_value (già in chaos)
# ---------------------------------------------------------------------------


def test_ask_chaos_equals_receive_value() -> None:
    q = _make_quote(receive_value=324.0)
    assert q.ask_chaos == pytest.approx(324.0)


def test_ask_chaos_none_when_receive_missing() -> None:
    q = _make_quote(pay_value=0.003, receive_value=None)
    assert q.ask_chaos is None


# ---------------------------------------------------------------------------
# mid_chaos: media bid/ask quando entrambi presenti
# ---------------------------------------------------------------------------


def test_mid_chaos_averages_both_sides() -> None:
    # Divine plausibile: bid=305, ask=325 → mid=315
    q = _make_quote(pay_value=1 / 305, receive_value=325.0)
    assert q.mid_chaos == pytest.approx((305 + 325) / 2, rel=1e-6)


def test_mid_chaos_falls_back_to_bid_if_only_bid() -> None:
    q = _make_quote(pay_value=0.5, receive_value=None)
    assert q.mid_chaos == pytest.approx(2.0)


def test_mid_chaos_falls_back_to_ask_if_only_ask() -> None:
    q = _make_quote(pay_value=None, receive_value=50.0)
    assert q.mid_chaos == pytest.approx(50.0)


def test_mid_chaos_none_when_both_missing() -> None:
    q = _make_quote(pay_value=None, receive_value=None)
    assert q.mid_chaos is None


# ---------------------------------------------------------------------------
# spread_pct
# ---------------------------------------------------------------------------


def test_spread_pct_basic() -> None:
    # bid=100, ask=110, mid=105, spread=10/105 ≈ 9.52%
    q = _make_quote(pay_value=1 / 100, receive_value=110.0)
    assert q.spread_pct == pytest.approx(10 / 105 * 100, rel=1e-4)


def test_spread_pct_zero_when_bid_equals_ask() -> None:
    q = _make_quote(pay_value=1 / 100, receive_value=100.0)
    assert q.spread_pct == pytest.approx(0.0, abs=1e-9)


def test_spread_pct_none_when_one_side_missing() -> None:
    q = _make_quote(pay_value=None, receive_value=100.0)
    assert q.spread_pct is None


# ---------------------------------------------------------------------------
# Serializzazione: i @computed_field devono apparire nel dump JSON
# ---------------------------------------------------------------------------


def test_derived_fields_appear_in_model_dump() -> None:
    """Importante per l'API: il frontend riceve bid/ask già calcolati."""
    q = _make_quote(pay_value=1 / 100, receive_value=110.0)
    dumped = q.model_dump()
    assert "bid_chaos" in dumped
    assert "ask_chaos" in dumped
    assert "mid_chaos" in dumped
    assert "spread_pct" in dumped
    assert dumped["bid_chaos"] == pytest.approx(100.0)
    assert dumped["ask_chaos"] == pytest.approx(110.0)
