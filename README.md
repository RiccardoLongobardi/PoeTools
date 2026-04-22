# FOB — Frusta Oracle Builder

Build planner AI per **Path of Exile 1** — interpreta richieste in linguaggio naturale (IT/EN), suggerisce build ottimali da poe.ninja, genera un piano di progressione dal livello 1 al 100 con costi reali via PoE Trade.

---

## Obiettivo

L'utente descrive il tipo di build che vuole (es. *"voglio ghiacciare tutto"*, *"martellone da slam"*, *"damage over time"*) e FOB:

1. **Interpreta** l'intento tramite NLP (keyword matching + categorizzazione)
2. **Identifica** le build candidate più forti su poe.ninja (top meta builds)
3. **Genera** una progressione 1→100: skill tree tappe, gem setup, gear priority
4. **Prezza** ogni item con query reali al PoE Trade API ufficiale

---

## Stack

- **Backend**: Python 3.12 · FastAPI · SQLAlchemy · APScheduler
- **Dati build**: poe.ninja builds API (scraping aggregato)
- **Prezzi item**: pathofexile.com/api/trade (query automatiche)
- **Package manager**: uv

---

## Struttura

```
backend/
├── __init__.py
├── main.py              # FastAPI app entry point
├── config.py            # Configurazione (league, endpoints)
├── db.py                # SQLAlchemy setup
├── models.py            # ORM models
├── scheduler.py         # APScheduler jobs
├── api/
│   ├── __init__.py
│   └── routes.py        # Endpoint /fob/oracle
├── datasource/
│   ├── __init__.py
│   ├── base.py          # Interfaccia DataSource astratta
│   └── poe_ninja.py     # Scraping poe.ninja builds
└── services/
    ├── __init__.py
    ├── intent.py        # NLP: parsing intento utente
    ├── pob_parser.py    # Parsing build data / PoB
    ├── fob_oracle.py    # Orchestratore principale
    ├── arbitrage.py     # (legacy - da separare)
    ├── faustus_intra.py # (legacy - da separare)
    ├── fetcher.py       # HTTP fetcher generico
    └── scheduler.py     # Logica scheduling
tests/
```

---

## API

### `POST /fob/oracle`

Riceve una richiesta in linguaggio naturale e restituisce build + progressione.

**Request body:**
```json
{
  "query": "voglio una build che ghiacci tutto, budget medio",
  "league": "Settlers"
}
```

**Response:**
```json
{
  "intent": {
    "damage_type": "cold",
    "style": "aoe",
    "budget": "medium"
  },
  "builds": [
    {
      "name": "Ice Nova Occultist",
      "class": "Witch",
      "pob_link": "...",
      "dps": 2500000,
      "ehp": 8000,
      "cost_chaos": 450
    }
  ],
  "progression": [
    {"level": 1, "note": "Frostbolt starter", "gems": ["Frostbolt", "Onslaught"]},
    {"level": 28, "note": "Swap a Ice Nova", "gems": ["Ice Nova", "Spell Echo", "Added Cold"]},
    {"level": 68, "note": "Endgame setup", "gems": ["Ice Nova", "Spell Echo", "Added Cold", "Hypothermia", "Cold Pen", "Controlled Destruction"]}
  ]
}
```

---

## Stato

**In sviluppo** — branch: `fob-frusta-oracle-builder`

| Modulo | Stato |
|--------|-------|
| Intent parsing (NLP) | Completo |
| poe.ninja scraping | Completo |
| Build ranking | Completo |
| Progressione 1→100 | Completo |
| PoE Trade pricing | Completo |
| API endpoint `/fob/oracle` | Completo |
| Frontend UI | Da fare |
