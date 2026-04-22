"""Implementazione concreta di `DataSource` contro poe.ninja.

Endpoint usati (tutti pubblici, nessuna auth):

    GET /api/data/currencyoverview?league=<LEAGUE>&type=Currency
    GET /api/data/currencyoverview?league=<LEAGUE>&type=Fragment
    GET /api/data/itemoverview?league=<LEAGUE>&type=Scarab   (fase successiva)

Shape della response (estratto, basato su documentazione community):

```
{
  "lines": [
    {
      "currencyTypeName": "Divine Orb",
      "pay": {
        "value": 225.5,        # quanti chaos paghi per 1 divine
        "listing_count": 180,
        ...
      },
      "receive": {
        "value": 220.0,        # quanti chaos ricevi per 1 divine (lato bid)
        "listing_count": 140,
        ...
      },
      "chaosEquivalent": 225.0,
      "lowConfidencePaySparkLine": {...},
      "detailsId": "divine-orb",
      ...
    },
    ...
  ],
  "currencyDetails": [
    {"id": 1, "name": "Chaos Orb", "tradeId": "chaos",
     "icon": "https://..."},
    ...
  ]
}
```

**Nota di cautela:** poe.ninja non ha documentazione ufficiale e alcuni
campi possono mancare. Ho marcato tutti i campi non-essenziali come
`Optional`, e il parser logga un warning invece di crashare se una riga
è malformata.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import settings
from backend.datasource.base import CurrencyInfo, DataSource, ExchangeQuote

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modelli "grezzi" che riflettono la shape di poe.ninja.
# Solo ad uso interno di questo modulo; fuori si parla in ExchangeQuote.
# ---------------------------------------------------------------------------


class _PoeNinjaPayReceive(BaseModel):
    """Blocco pay/receive di una `line` di poe.ninja."""

    value: float | None = None
    listing_count: int | None = None
    # campi extra sono ignorati (model_config extra=ignore di default in v2)


class _PoeNinjaCurrencyLine(BaseModel):
    """Una riga di `currencyoverview.lines`."""

    currency_type_name: str = Field(alias="currencyTypeName")
    pay: _PoeNinjaPayReceive | None = None
    receive: _PoeNinjaPayReceive | None = None
    chaos_equivalent: float = Field(alias="chaosEquivalent")
    # `detailsId` è lo slug che combacia con currencyDetails.tradeId
    details_id: str | None = Field(default=None, alias="detailsId")
    # poe.ninja popola SEMPRE entrambi i set di sparkline: uno "regolare" e uno
    # "lowConfidence" di fallback. Il vero segnale di low-confidence è quando
    # il regolare manca e c'è solo il fallback — quindi dobbiamo modellare
    # entrambi per confrontarli.
    pay_spark_line: dict[str, Any] | None = Field(default=None, alias="paySparkLine")
    receive_spark_line: dict[str, Any] | None = Field(
        default=None, alias="receiveSparkLine"
    )
    low_confidence_pay_spark_line: dict[str, Any] | None = Field(
        default=None, alias="lowConfidencePaySparkLine"
    )
    low_confidence_receive_spark_line: dict[str, Any] | None = Field(
        default=None, alias="lowConfidenceReceiveSparkLine"
    )

    model_config = ConfigDict(populate_by_name=True)


class _PoeNinjaCurrencyDetail(BaseModel):
    """Un entry di `currencyoverview.currencyDetails`."""

    id: int
    name: str
    trade_id: str | None = Field(default=None, alias="tradeId")
    icon: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class _PoeNinjaCurrencyOverview(BaseModel):
    """Response completa di `/currencyoverview`."""

    lines: list[_PoeNinjaCurrencyLine]
    currency_details: list[_PoeNinjaCurrencyDetail] = Field(
        default_factory=list, alias="currencyDetails"
    )

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Implementazione
# ---------------------------------------------------------------------------


class PoeNinjaSource(DataSource):
    """Fonte dati poe.ninja. Async, retry-aware, gentile coi rate limit."""

    def __init__(
        self,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.poe_ninja_base_url).rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_s or settings.http_timeout_s,
            headers={"User-Agent": user_agent or settings.http_user_agent},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------ API

    async def list_currencies(self, league: str) -> list[CurrencyInfo]:
        # Le currency "core" sono nel type=Currency; prendiamo anche Fragment
        # per completezza (oggetti come Offering, Breachstone, ecc. sono tradable).
        #
        # IMPORTANTE: il trade_id di catalogo DEVE coincidere con quello
        # generato da `_lines_to_quotes`, altrimenti `fetch_and_store` droppa
        # snapshot in silenzio (la Currency row non si trova per lookup).
        # Per questo iteriamo `lines` (non `currencyDetails`) e usiamo la stessa
        # helper `_derive_trade_id`. Gli icon/display_name li peschiamo da
        # `currencyDetails` tramite il nome della currency.
        out: list[CurrencyInfo] = []
        for category, ep_type in [("Currency", "Currency"), ("Fragment", "Fragment")]:
            raw = await self._get_currency_overview(league=league, ep_type=ep_type)
            details_by_name = {d.name: d for d in raw.currency_details}
            for line in raw.lines:
                trade_id = _derive_trade_id(line, details_by_name)
                if not trade_id:
                    continue
                details = details_by_name.get(line.currency_type_name)
                out.append(
                    CurrencyInfo(
                        trade_id=trade_id,
                        display_name=details.name if details else line.currency_type_name,
                        icon_url=details.icon if details else None,
                        category=category,
                    )
                )
        # Dedup per trade_id: può capitare che una currency appaia in entrambe le liste.
        seen: set[str] = set()
        deduped: list[CurrencyInfo] = []
        for c in out:
            if c.trade_id in seen:
                continue
            seen.add(c.trade_id)
            deduped.append(c)
        return deduped

    async def fetch_currency_overview(self, league: str) -> list[ExchangeQuote]:
        raw = await self._get_currency_overview(league=league, ep_type="Currency")
        return self._lines_to_quotes(raw, league=league)

    async def fetch_fragment_overview(self, league: str) -> list[ExchangeQuote]:
        raw = await self._get_currency_overview(league=league, ep_type="Fragment")
        return self._lines_to_quotes(raw, league=league)

    # ------------------------------------------------------------------ guts

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.0, min=1.0, max=10.0),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _get_currency_overview(
        self, *, league: str, ep_type: str
    ) -> _PoeNinjaCurrencyOverview:
        url = f"{self._base_url}/currencyoverview"
        params = {"league": league, "type": ep_type}
        log.debug("GET %s %s", url, params)
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return _PoeNinjaCurrencyOverview.model_validate(data)

    def _lines_to_quotes(
        self, raw: _PoeNinjaCurrencyOverview, *, league: str
    ) -> list[ExchangeQuote]:
        now = datetime.now(tz=timezone.utc)
        details_by_name = {d.name: d for d in raw.currency_details}

        quotes: list[ExchangeQuote] = []
        for line in raw.lines:
            trade_id = _derive_trade_id(line, details_by_name)
            if not trade_id:
                continue
            # Low-confidence = regular sparkline assente e fallback presente.
            # Se il regolare c'è, poe.ninja ha dati sufficienti e non flagghiamo.
            has_regular = bool(line.pay_spark_line or line.receive_spark_line)
            has_fallback = bool(
                line.low_confidence_pay_spark_line
                or line.low_confidence_receive_spark_line
            )
            low_conf = not has_regular and has_fallback
            try:
                quotes.append(
                    ExchangeQuote(
                        currency_trade_id=trade_id,
                        league=league,
                        fetched_at=now,
                        chaos_equivalent=line.chaos_equivalent,
                        pay_value=line.pay.value if line.pay else None,
                        receive_value=line.receive.value if line.receive else None,
                        pay_listing_count=(
                            line.pay.listing_count if line.pay else None
                        ),
                        receive_listing_count=(
                            line.receive.listing_count if line.receive else None
                        ),
                        low_confidence=low_conf,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — volutamente permissivi
                log.warning(
                    "Skipping malformed line %r: %s", line.currency_type_name, exc
                )
        return quotes


def _derive_trade_id(
    line: _PoeNinjaCurrencyLine,
    details_by_name: dict[str, _PoeNinjaCurrencyDetail],
) -> str:
    """Deriva un trade_id stabile per una `line`.

    Priorità:
      1. `line.details_id` — lo slug che poe.ninja mette direttamente nelle lines
         (es. "divine-orb"). È la chiave canonica del loro sistema interno.
      2. `currencyDetails[name].tradeId` — lo slug di pathofexile.com/trade
         (es. "divine"). Usato come fallback quando details_id manca.
      3. Slug generato dal nome — fallback robusto se poe.ninja non ci dà niente.

    Lo usiamo sia in `list_currencies` che in `_lines_to_quotes` per garantire
    che catalogo e snapshot usino lo STESSO id — altrimenti il fetcher droppa
    snapshot in silenzio per "unknown trade_id".
    """
    if line.details_id:
        return line.details_id
    details = details_by_name.get(line.currency_type_name)
    if details and details.trade_id:
        return details.trade_id
    return _slugify(line.currency_type_name)


def _slugify(name: str) -> str:
    """Fallback slug se poe.ninja non ci dà il tradeId.

    Conservativo: solo minuscole + hyphen + alphanum. Niente magie unicode.
    """
    out = []
    prev_hyphen = False
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
            prev_hyphen = False
        elif not prev_hyphen:
            out.append("-")
            prev_hyphen = True
    return "".join(out).strip("-")
