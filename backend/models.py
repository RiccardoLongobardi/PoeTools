"""SQLAlchemy models — lo schema dello storico locale.

Design principle: ogni fetch scrive righe **immutabili** timestampate.
Non sovrascrivi mai lo storico; le query UI fanno aggregazioni on-the-fly.
Questo costa pochi MB a settimana e ti dà rewind gratis.

Tabelle:
    currency          — anagrafica delle currency (nome, icon, tradeId)
    exchange_snapshot — una riga per ogni fetch: chaos_equiv, pay_value,
                        receive_value, volume, ecc. per una coppia
                        (currency -> chaos) o (pay -> receive) a un certo istante
    manual_quote      — quote inseriti dall'utente mentre è in Faustus in-game
    watchlist_item    — coppie che l'utente tiene d'occhio, con soglia profit%
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class Currency(Base):
    """Anagrafica di una currency scambiabile."""

    __tablename__ = "currency"

    id: Mapped[int] = mapped_column(primary_key=True)
    # `trade_id` è il nome slug usato dall'API (es. "chaos", "divine")
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # `display_name` è il nome human-readable ("Chaos Orb", "Divine Orb")
    display_name: Mapped[str] = mapped_column(String(128))
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # `category` distingue "Currency", "Fragment", "Scarab", ecc.
    category: Mapped[str] = mapped_column(String(32), index=True)

    snapshots: Mapped[list["ExchangeSnapshot"]] = relationship(
        back_populates="currency", cascade="all, delete-orphan"
    )


class ExchangeSnapshot(Base):
    """Una riga = stato del mercato di UNA currency verso chaos a un certo istante.

    Il tasso verso chaos è il comune denominatore: da `chaos_equivalent` di
    tutte le currency puoi ricostruire qualsiasi cross (A->B = eq_A / eq_B),
    che è esattamente quello che serve al detector di arbitrage.

    pay_value / receive_value sono i rate grezzi (quanta currency paghi per
    averne 1 chaos, e quanta ne ricevi per 1 chaos), utili per vedere lo
    spread bid/ask.
    """

    __tablename__ = "exchange_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency_id: Mapped[int] = mapped_column(
        ForeignKey("currency.id", ondelete="CASCADE"), index=True
    )
    league: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Rate aggregati vs chaos orb
    chaos_equivalent: Mapped[float] = mapped_column(Float)
    # Bid/ask visti dal lato "pay" (quanto paghi per ottenere 1 unità di chaos)
    pay_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # (quanto ricevi in currency per 1 chaos pagato)
    receive_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Indicatori di confidenza / volume
    pay_listing_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receive_listing_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)

    currency: Mapped[Currency] = relationship(back_populates="snapshots")

    __table_args__ = (
        # Un solo snapshot per currency/lega/istante — dedup difensiva
        UniqueConstraint("currency_id", "league", "fetched_at", name="uq_snapshot"),
        Index("ix_snapshot_league_time", "league", "fetched_at"),
    )


class ManualQuote(Base):
    """Quote inserita manualmente dall'utente mentre è in-game presso Faustus.

    A differenza degli snapshot, questi sono fresh: rappresentano quello che
    l'utente *vede adesso* nella UI di Faustus. Il tool li confronta con il
    fair value storico per dire "accetta" o "aspetta".
    """

    __tablename__ = "manual_quote"

    id: Mapped[int] = mapped_column(primary_key=True)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
    league: Mapped[str] = mapped_column(String(64), index=True)
    # Coppia: "pagheresti X di `pay` per ricevere Y di `receive`"
    pay_currency_id: Mapped[int] = mapped_column(ForeignKey("currency.id"))
    receive_currency_id: Mapped[int] = mapped_column(ForeignKey("currency.id"))
    pay_amount: Mapped[float] = mapped_column(Float)
    receive_amount: Mapped[float] = mapped_column(Float)
    # Nota libera dell'utente ("top bid", "sotto 2° offerta", ecc.)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)


class WatchlistItem(Base):
    """Coppia sorvegliata. Alert quando last snapshot mostra profit > threshold."""

    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    pay_currency_id: Mapped[int] = mapped_column(ForeignKey("currency.id"))
    receive_currency_id: Mapped[int] = mapped_column(ForeignKey("currency.id"))
    # Soglia di profit% per alert (es. 2.5 = 2.5%)
    threshold_pct: Mapped[float] = mapped_column(Float, default=2.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "pay_currency_id", "receive_currency_id", name="uq_watchlist_pair"
        ),
    )
