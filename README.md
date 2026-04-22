# Faustus Dashboard

Market intelligence desktop app per il **Currency Exchange** di Faustus in Path of Exile 1.
Lega target: Mirage (3.28) softcore.

Non è un "arbitrage sniper" real-time (che sarebbe bot, e tecnicamente non è permesso).
È una **dashboard offline** che legge i dati di mercato aggregati e:

- ti mostra overview, trend e volume per ogni currency scambiabile via Faustus;
- trova **cicli triangolari** (es. `divine → exalt → chaos → divine`) con profitto persistente su più ore;
- ti permette di inserire manualmente una quote che vedi in gioco, e ti dice se è sopra/sotto il fair value storico;
- tiene una watchlist con alert desktop quando le coppie preferite mostrano spread interessanti.

---

## Perché poe.ninja e non l'API GGG ufficiale

GGG ha un endpoint pubblico per la history del Currency Exchange
(`pathofexile.com/developer/docs/reference`) ma l'accesso richiede:

1. OAuth 2.0 client credentials, registrazione via email a `oauth@grindinggear.com`.
2. Approvazione manuale da parte del team GGG (low priority, settimane-mesi).
3. Lo scope per i dati di mercato è in `service:*` — **non disponibile per client pubblici**,
   solo per partner ufficiali (fra cui poe.ninja).

Risultato: per un tool personale, la via diretta a GGG è praticamente chiusa.
poe.ninja è un partner ufficiale che ri-espone i dati aggregati su endpoint REST senza auth.
Usiamo loro come fonte primaria.

Il codice è organizzato attorno a un'interfaccia `DataSource` astratta: se un giorno
ottieni l'OAuth GGG, basta aggiungere un'implementazione `GGGOfficialSource` senza
toccare il resto.

---

## Architettura

```
┌─────────────────────────────────────────────┐
│          PyWebView desktop window            │
│  ┌─────────────────────────────────────┐    │
│  │   React dashboard (served locally)   │    │
│  └──────────────┬──────────────────────┘    │
│                 │ HTTP (localhost)           │
│  ┌──────────────▼──────────────────────┐    │
│  │   FastAPI backend                    │    │
│  └──────┬──────────────────┬────────────┘    │
│         │                   │                 │
│  ┌──────▼────────┐   ┌─────▼───────────┐    │
│  │ APScheduler   │   │ SQLite DB        │    │
│  │ hourly fetch  │◄──┤ exchange_history │    │
│  └──────┬────────┘   │ currencies       │    │
│         │            │ manual_quotes    │    │
│         ▼            │ watchlist        │    │
│  ┌──────────────┐    └──────────────────┘    │
│  │ poe.ninja    │                            │
│  │ (no auth)    │                            │
│  └──────────────┘                            │
└──────────────────────────────────────────────┘
```

### Stack

| Livello   | Scelta                                     | Perché                                          |
|-----------|--------------------------------------------|-------------------------------------------------|
| Runtime   | Python 3.11+                               | Ecosistema dati, async nativo                   |
| HTTP      | `httpx` async                              | Moderno, retry/timeout facili                   |
| API       | `FastAPI` + `pydantic v2`                  | Type-safe, validation gratis, OpenAPI gratis    |
| DB        | SQLite + SQLAlchemy 2.0                    | Zero ops, file singolo, sufficient per 1 utente |
| Scheduler | `APScheduler`                              | Job orario, cron-like, integrato con asyncio    |
| Frontend  | React 18 + Vite + TypeScript               | Standard moderno, Riccardo può estendere        |
| Charts    | Recharts                                   | Dichiarativo, buoni default                     |
| Packaging | PyWebView (backend + bundle frontend)      | Finestra desktop nativa, zero Electron bloat    |

---

## Roadmap

- **Fase 0 — Scaffolding + Data source.**
  Struttura progetto, `DataSource` astratto, `PoeNinjaSource` stub, fixture di test.
  *(in corso)*
- **Fase 1 — Data layer.**
  Schema SQLite, fetcher, scheduler orario, gestione ratelimit.
- **Fase 2 — Arbitrage engine.**
  Grafo di scambio, Bellman-Ford per cicli negativi, scoring dei cicli per profitto
  x volume x persistenza.
- **Fase 3 — Dashboard web.**
  React app: overview, pair explorer, arbitrage table, manual quote input.
- **Fase 4 — Desktop bundle + polish.**
  PyWebView, icona, watchlist, alert desktop.

---

## Come si usa (una volta completato)

### Prerequisiti

- Python 3.11+
- Node.js 20+
- `uv` (gestore pacchetti Python moderno, `pip install uv` oppure
  [curl | sh](https://docs.astral.sh/uv/getting-started/installation/))

### Setup backend

```bash
cd faustus-dashboard
uv sync                                 # installa dipendenze Python
uv run faustus init-db                  # crea SQLite schema
uv run faustus fetch-once --league Mirage  # primo fetch manuale
uv run faustus serve                    # avvia FastAPI su 127.0.0.1:8765
```

### Setup frontend

```bash
cd frontend
npm install
npm run dev                             # Vite dev server su 5173, parla col backend
```

### Desktop app bundle (fase 4)

```bash
uv run faustus desktop                  # apre finestra PyWebView
```

---

## Struttura directory

```
faustus-dashboard/
├── README.md
├── pyproject.toml
├── .gitignore
├── backend/
│   ├── __init__.py
│   ├── main.py               # entrypoint CLI + serve
│   ├── config.py             # pydantic-settings
│   ├── db.py                 # SQLAlchemy engine + session
│   ├── models.py             # tabelle DB
│   ├── datasource/
│   │   ├── __init__.py
│   │   ├── base.py           # interfaccia DataSource
│   │   └── poe_ninja.py      # implementazione poe.ninja
│   ├── services/
│   │   ├── __init__.py
│   │   ├── fetcher.py        # orchestrazione fetch → DB
│   │   └── arbitrage.py      # detection cicli (fase 2)
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py         # endpoints FastAPI
│   └── scheduler.py          # APScheduler wiring
├── frontend/                 # React app (fase 3)
│   └── (vuoto per ora)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_datasource_poe_ninja.py
    └── fixtures/
        └── currencyoverview_mirage_sample.json
```

---

## Note di design

- **DataSource è l'unica cosa che può parlare con l'esterno.** Il resto del codice
  lavora su modelli Pydantic interni. Questo rende triviale swappare fonte dati o
  mockare nei test.
- **Il DB è sorgente di verità per lo storico.** Ogni fetch scrive righe immutabili
  timestampate; le query UI leggono sempre dal DB, mai dalla rete.
- **Il calcolo arbitrage è stateless puro.** Prende in input uno snapshot
  (dict di rates) e ritorna cicli. Facile da testare, facile da parallelizzare
  se mai servisse.
- **PyWebView è *opzionale*** — il prodotto funziona benissimo come "local web app"
  aprendo `http://127.0.0.1:5173` nel browser. Il bundle desktop è solo cosmesi.

---

## Faustus intra-NPC flipper

Oltre all'engine basato su poe.ninja (`backend/services/arbitrage.py`), che confronta
un Faustus "teorico" (mid-price based) col bridge via chaos del mercato, esiste un
engine separato pensato solo per il **flipping intra-Faustus**.

- Modulo: `backend/services/faustus_intra.py`
- Input: lista di `FaustusRate(source_trade_id, target_trade_id, rate)`, dove
  `rate` è quante unità di `target_trade_id` dà Faustus per 1 unità di
  `source_trade_id`.
- Output: lista di `FaustusCycle(path, profit_pct, step_rates)` ordinati per
  profit decrescente.

Esempio minimale di utilizzo:

```python
from backend.services.faustus_intra import FaustusRate, find_faustus_cycles

rates = [
    FaustusRate("divine-orb", "fracturing-orb", 2.5),
    FaustusRate("fracturing-orb", "divine-orb", 1 / 2.15),
]

cycles = find_faustus_cycles(rates, min_profit_pct=1.0)
for c in cycles:
    print(c.path, c.profit_pct)
# path ~ ('divine-orb', 'fracturing-orb', 'divine-orb'), profit_pct ~ 16.3
```

Questo engine è completamente indipendente dai dati poe.ninja / DB: è pensato per
essere alimentato da rate misurati in-game direttamente sull'NPC Faustus.
