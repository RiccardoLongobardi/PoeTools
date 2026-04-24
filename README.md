# FOB — Frusta Oracle Builder

Build planner AI per **Path of Exile 1** — interpreta richieste in linguaggio naturale (IT/EN), suggerisce build ottimali da poe.ninja, genera un piano di progressione dal livello 1 al 100 con costi reali via PoE Trade.

---

## Obiettivo

L'utente descrive il tipo di build che vuole (es. *"voglio ghiacciare tutto"*, *"martellone da slam"*, *"damage over time"*) e FOB:

1. **Interpreta** l'intento tramite NLP (keyword matching + categorizzazione)
2. **Identifica** le build candidate più forti da cache locale (poe.ninja, ladder)
3. **Genera** una progressione 1→100: skill tree tappe, gem setup, gear priority
4. **Prezza** ogni item con query reali al PoE Trade API ufficiale

---

## Run locale

```bash
# Installa dipendenze
uv sync

# Avvia il backend
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

L'app sarà disponibile su:
- **UI web**: http://localhost:8000/app
- **API docs**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

---

## Stack

- **Backend**: Python 3.12 · FastAPI · SQLAlchemy · APScheduler
- **Dati build**: cache locale da poe.ninja + ladder PoE (refresh manuale/schedulato)
- **Prezzi item**: pathofexile.com/api/trade (query automatiche)
- **Package manager**: uv

---

## Struttura

```
backend/
├── __init__.py
├── main.py              # FastAPI app entry point + mount frontend
├── config.py            # Configurazione (league, endpoints)
├── db.py                # SQLAlchemy setup
├── models.py            # ORM models
├── scheduler.py         # APScheduler jobs
├── api/
│   ├── __init__.py
│   ├── routes.py        # Endpoint /fob/oracle
│   └── admin_routes.py  # Endpoint admin (refresh cache, stato)
├── datasource/
│   ├── __init__.py
│   ├── base.py          # Interfaccia DataSource astratta
│   └── poe_ninja.py     # Scraping poe.ninja builds
└── services/
    ├── __init__.py
    ├── intent.py        # NLP: parsing intento utente
    ├── pob_parser.py    # Parsing build data / PoB
    ├── fob_oracle.py    # Orchestratore principale (cache → ladder → fallback)
    ├── cache_store.py   # Lettura/scrittura cache build su disco
    ├── refresh_service.py # Logica refresh build da fonti esterne
    ├── arbitrage.py     # (legacy - da separare)
    ├── faustus_intra.py # (legacy - da separare)
    ├── fetcher.py       # HTTP fetcher generico
    └── scheduler.py     # Logica scheduling
frontend/
└── index.html           # UI web single-page (servita su /app)
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
  "league": "Mirage"
}
```

**Response:**
```json
{
  "intent": {
    "damage_type": ["cold"],
    "style": ["aoe"],
    "budget": "medium"
  },
  "builds": [
    {
      "name": "Ice Nova Occultist",
      "ascendancy": "Occultist",
      "main_skill": "Ice Nova",
      "source": "poe_ninja",
      "score": 0.92,
      "est_cost_div": 15,
      "league": "Mirage",
      "url": "..."
    }
  ],
  "plan": {
    "levelling_stages": [
      {"level_range": "1-28", "title": "Frostbolt starter", "support_gems": ["Onslaught", "Added Cold"]},
      {"level_range": "28-68", "title": "Swap a Ice Nova", "support_gems": ["Spell Echo", "Added Cold", "Hypothermia"]},
      {"level_range": "68-100", "title": "Endgame setup", "support_gems": ["Spell Echo", "Added Cold", "Hypothermia", "Cold Pen", "Controlled Destruction"]}
    ],
    "total_cost_div": 15
  }
}
```

### `GET /health`

```json
{"status": "ok", "league": "Mirage"}
```

---

## Admin — Cache

L'Oracle usa una cache locale su disco (`data/builds_cache_<league>.json`). Se la cache è vuota o stale, le build restituite sono quelle hardcoded di fallback.

### `GET /fob/admin/cache/status?league=Mirage`

Restituisce stato della cache per la league specificata (auth richiesta).

```json
{
  "league": "Mirage",
  "total_builds": 120,
  "last_refresh_at": "2026-04-24T10:00:00Z",
  "sources": {
    "poe_ninja": {"status": "ok", "count": 100},
    "ladder":    {"status": "ok", "count": 20}
  }
}
```

### `POST /fob/admin/refresh`

Lancia il refresh della cache (auth richiesta).

```json
{
  "league": "Mirage",
  "limit_per_source": 100
}
```

### Auth admin

Credenziali di default:
- **user**: `admin`
- **password**: `fob`

Override tramite variabili d'ambiente:
```bash
export FOB_ADMIN_USER=miouser
export FOB_ADMIN_PASS=miapassword
```

---

## Stato

**In sviluppo** — branch: `fob-frusta-oracle-builder`

| Modulo | Stato |
|--------|-------|
| Intent parsing (NLP) | ✅ Completo |
| poe.ninja scraping | ✅ Completo |
| Build ranking | ✅ Completo |
| Progressione 1→100 | ✅ Completo |
| PoE Trade pricing | ✅ Completo |
| API endpoint `/fob/oracle` | ✅ Completo |
| Cache su disco + refresh | ✅ Completo |
| Admin endpoints | ✅ Completo |
| Frontend UI (`/app`) | ✅ Completo |
| Adapter Maxroll/Mobalytics | 🔜 V2 |
| APScheduler refresh automatico | 🔜 V2 |
