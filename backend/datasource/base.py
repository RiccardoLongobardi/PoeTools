"""Interfaccia astratta di una fonte dati del currency exchange.

Definisce i modelli Pydantic interni usati dal resto dell'app, e la firma
dei metodi che qualsiasi provider concreto (poe.ninja oggi, GGG domani)
deve implementare.

**Design principle:** queste Pydantic sono il *nostro* formato canonico,
non quello di poe.ninja. Ogni provider concreto si occupa di convertire
la sua response in questi modelli. In questo modo, se poe.ninja cambia
schema, o se aggiungiamo un provider con campi diversi, il resto del
codice (fetcher, arbitrage engine, API) non se ne accorge nemmeno.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class CurrencyInfo(BaseModel):
    """Anagrafica di una currency: chi è, come si chiama, icona."""

    trade_id: str = Field(description="Slug machine-readable, es. 'chaos', 'divine'.")
    display_name: str = Field(description="Nome human-readable, es. 'Chaos Orb'.")
    icon_url: str | None = None
    # "Currency", "Fragment", "Scarab" ecc. — utile per filtrare la UI
    category: str = "Currency"


class ExchangeQuote(BaseModel):
    """Stato aggregato del mercato per una currency in un dato istante.

    Tutto è espresso *rispetto a chaos orb* come denominatore comune.
    Da qui l'arbitrage engine ricostruisce qualsiasi cross-pair
    (es. divine/exalt = divine_eq / exalt_eq).
    """

    currency_trade_id: str
    league: str
    fetched_at: datetime

    # Prezzo medio della currency in chaos (es. divine = 225c)
    chaos_equivalent: float

    # Bid/ask grezzi. Semantica:
    #  - pay_value:    quanti `currency` servono per ottenere 1 chaos
    #                  (= 1 / price_if_you_want_to_sell)
    #  - receive_value: quanti `currency` ottieni pagando 1 chaos
    # Spread = pay_value vs receive_value (se molto distanti = mercato illiquido)
    pay_value: float | None = None
    receive_value: float | None = None

    pay_listing_count: int | None = None
    receive_listing_count: int | None = None

    # Flag poe.ninja: troppo pochi sample per fidarsi
    low_confidence: bool = False

    # -- Derived (in chaos) ------------------------------------------------
    # Tutti i consumer dell'app vogliono parlare di prezzi *in chaos*, non
    # dei reciproci raw di poe.ninja. Esponiamo qui una volta per tutte
    # l'inversione — così frontend, arbitrage engine e alert non la rifanno.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bid_chaos(self) -> float | None:
        """Prezzo bid in chaos (= 1 / pay_value).

        "Bid" = prezzo a cui il mercato è disposto a *comprare* questa
        currency da te. Se vendi, ottieni questo.

        None se pay_value è None o 0 (currency senza lato bid attivo).
        """
        if not self.pay_value:
            return None
        return 1.0 / self.pay_value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ask_chaos(self) -> float | None:
        """Prezzo ask in chaos (= receive_value).

        "Ask" = prezzo a cui il mercato è disposto a *venderti* questa
        currency. Se compri, paghi questo.

        None se receive_value è None.
        """
        return self.receive_value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid_chaos(self) -> float | None:
        """Mid-price in chaos. Media aritmetica di bid e ask quando entrambi
        sono presenti; altrimenti ritorna il lato disponibile.

        `chaos_equivalent` di poe.ninja è già un mid ponderato — ma noi ne
        facciamo uno "onesto" dai soli bid/ask per verifica incrociata.
        """
        b, a = self.bid_chaos, self.ask_chaos
        if b is not None and a is not None:
            return (b + a) / 2.0
        return b if b is not None else a

    @computed_field  # type: ignore[prop-decorator]
    @property
    def spread_pct(self) -> float | None:
        """Spread bid/ask in percentuale del mid.

        Usato come proxy di liquidità: spread grande = currency illiquida,
        arbitraggi su di lei sono fragili. Il frontend può mettere una soglia
        (es. >10% = flag warning).

        None se uno dei due lati manca.
        """
        b, a = self.bid_chaos, self.ask_chaos
        if b is None or a is None:
            return None
        mid = (b + a) / 2.0
        if mid == 0:
            return None
        return abs(a - b) / mid * 100.0


class DataSource(ABC):
    """Interfaccia astratta di un provider di market data.

    Ogni implementazione deve:
    1. Sapere come parlare con la propria fonte esterna (HTTP, file, ecc.)
    2. Convertire la response nei modelli Pydantic di cui sopra
    3. Essere async-safe
    """

    @abstractmethod
    async def list_currencies(self, league: str) -> list[CurrencyInfo]:
        """Ritorna l'anagrafica di tutte le currency tradabili nella lega.

        Usato al primo avvio per popolare la tabella `currency`, e ad ogni
        league change per aggiornare eventuali nuove entry.
        """

    @abstractmethod
    async def fetch_currency_overview(self, league: str) -> list[ExchangeQuote]:
        """Ritorna lo snapshot corrente delle currency "core" (Orb, Shards).

        Tipo = "Currency" nella terminologia poe.ninja.
        """

    @abstractmethod
    async def fetch_fragment_overview(self, league: str) -> list[ExchangeQuote]:
        """Ritorna lo snapshot corrente dei fragment (Offering, Breachstone, ecc.)."""

    async def fetch_all(self, league: str) -> list[ExchangeQuote]:
        """Helper che aggrega tutte le categorie. Override se serve custom."""
        currency = await self.fetch_currency_overview(league)
        fragment = await self.fetch_fragment_overview(league)
        return currency + fragment

    async def aclose(self) -> None:
        """Cleanup opzionale (chiusura client HTTP, ecc.). Default no-op."""
